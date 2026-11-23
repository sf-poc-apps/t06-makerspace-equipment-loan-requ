import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.loan import TOOLS, LoanRequest
from app.main import app, store
from app.service import create_request, decide


def client(role="Member"):
    c = TestClient(app)
    c.cookies.set("role", role)
    return c


def make_payload(**over):
    data = {"member_name": "Ana", "tool": "3D Printer", "start_date": "2026-12-01",
            "end_date": "2026-12-05", "reason": "Prototype a case"}
    data.update(over)
    return data


def make_request(**over):
    return create_request(store, LoanRequest(**make_payload(**over)))


def find(title):
    rows = [r for r in store.list("requests") if r["member_name"] == title]
    return rows[0] if rows else None


# --- Unit: tool validation ---

@pytest.mark.parametrize("bad", ["", "  ", "Chainsaw", "3d printer"])
def test_tool_validation_rejects_unknown(bad):
    with pytest.raises(ValidationError):
        LoanRequest(**make_payload(tool=bad))


def test_tool_validation_accepts_fixed_list():
    for tool in TOOLS:
        assert LoanRequest(**make_payload(tool=tool)).tool == tool


def test_missing_or_invalid_fields_rejected():
    with pytest.raises(ValidationError):
        LoanRequest(**make_payload(member_name=""))
    with pytest.raises(ValidationError):
        LoanRequest(**make_payload(reason=""))
    with pytest.raises(ValidationError):
        LoanRequest(**make_payload(start_date="not-a-date"))
    with pytest.raises(ValidationError):
        LoanRequest(**make_payload(start_date="2026-02-30"))


# --- Unit: decision logic ---

def test_decide_without_note_raises_and_status_unchanged():
    req = make_request()
    with pytest.raises(ValueError):
        decide(store, req["id"], "Approved", "   ")
    assert store.get("requests", req["id"])["status"] == "Pending"


def test_decide_writes_history_entry():
    req = make_request()
    updated = decide(store, req["id"], "Approved", "Approved for the workshop")
    assert updated["status"] == "Approved"
    history = updated["history"]
    assert len(history) == 2
    entry = history[-1]
    assert entry["status"] == "Approved"
    assert entry["note"] == "Approved for the workshop"
    assert entry["role"] == "Approver"
    assert entry["timestamp"]
    first = history[0]
    assert first["status"] == "Pending" and first["note"] == "Submitted" and first["role"] == "Member"


def test_decide_twice_refused():
    req = make_request()
    decide(store, req["id"], "Rejected", "No")
    with pytest.raises(ValueError):
        decide(store, req["id"], "Approved", "Wait")


# --- HTTP: health ---

def test_health():
    assert client().get("/healthz").status_code == 200


# --- HTTP: create ---

def test_create_success_pending():
    before = len(store.list("requests"))
    r = client("Member").post("/requests", data=make_payload(), follow_redirects=False)
    assert r.status_code == 303
    req = store.list("requests")[-1]
    assert req["status"] == "Pending"
    assert len(store.list("requests")) == before + 1


def test_create_invalid_tool_rejected():
    before = len(store.list("requests"))
    r = client("Member").post("/requests", data=make_payload(tool="Chainsaw"))
    assert r.status_code == 422
    assert len(store.list("requests")) == before


def test_create_missing_field_rejected():
    r = client("Member").post("/requests", data={"member_name": "Ana", "tool": "3D Printer"})
    assert r.status_code == 422


# --- HTTP: role gating ---

def test_submit_blocked_for_viewer_and_approver():
    r = client("Viewer").post("/requests", data=make_payload())
    assert r.status_code == 403
    r = client("Approver").post("/requests", data=make_payload())
    assert r.status_code == 403


def test_new_form_gated_to_member():
    assert client("Viewer").get("/requests/new").status_code == 403
    assert client("Approver").get("/requests/new").status_code == 403
    assert client("Member").get("/requests/new").status_code == 200


def test_decision_blocked_for_member_and_viewer():
    req = make_request()
    for role in ("Member", "Viewer"):
        r = client(role).post(f"/requests/{req['id']}/decision",
                              data={"decision": "Approved", "note": "x"})
        assert r.status_code == 403
    assert store.get("requests", req["id"])["status"] == "Pending"


# --- HTTP: decision flow ---

def test_decision_success_and_second_refused():
    req = make_request()
    c = client("Approver")
    r = c.post(f"/requests/{req['id']}/decision",
               data={"decision": "Approved", "note": "Fine by me"}, follow_redirects=False)
    assert r.status_code == 303
    assert store.get("requests", req["id"])["status"] == "Approved"
    r = c.post(f"/requests/{req['id']}/decision",
               data={"decision": "Rejected", "note": "Reconsidered"})
    assert r.status_code == 400
    assert store.get("requests", req["id"])["status"] == "Approved"


def test_decision_without_note_rejected():
    req = make_request()
    r = client("Approver").post(f"/requests/{req['id']}/decision", data={"decision": "Approved"})
    assert r.status_code == 422
    assert store.get("requests", req["id"])["status"] == "Pending"


def test_decision_missing_request_404():
    with pytest.raises(LookupError):
        decide(store, "nope", "Approved", "x")
    r = client("Approver").post("/requests/nope/decision",
                               data={"decision": "Approved", "note": "x"})
    assert r.status_code == 404


# --- HTTP: list and detail ---

def test_list_shows_all_roles_and_status():
    make_request(member_name="ListUser")
    for role in ("Member", "Approver", "Viewer"):
        r = client(role).get("/")
        assert r.status_code == 200
        assert "ListUser" in r.text


def test_detail_shows_history_for_all_roles():
    req = make_request(member_name="HistUser")
    decide(store, req["id"], "Rejected", "Too busy that week")
    for role in ("Member", "Approver", "Viewer"):
        r = client(role).get(f"/requests/{req['id']}")
        assert r.status_code == 200
        assert "Submitted" in r.text
        assert "Too busy that week" in r.text
        assert "Approver" in r.text
    detail = client("Viewer").get(f"/requests/{req['id']}").text
    assert detail.index("Submitted") < detail.index("Too busy that week")


def test_detail_404_unknown():
    assert client().get("/requests/missing").status_code == 404


def test_decided_request_offers_no_action():
    req = make_request(member_name="DecidedUser")
    decide(store, req["id"], "Approved", "ok")
    r = client("Approver").get(f"/requests/{req['id']}")
    assert "decision" not in r.text


def test_pending_detail_offers_action_to_approver_only():
    req = make_request(member_name="PendUser")
    assert "/decision" in client("Approver").get(f"/requests/{req['id']}").text
    assert "/decision" not in client("Viewer").get(f"/requests/{req['id']}").text
    assert "/decision" not in client("Member").get(f"/requests/{req['id']}").text


# --- HTTP: role switcher ---

def test_role_switcher():
    r = client("Viewer").post("/role", data={"role": "Member"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.cookies["role"] == "Member"


def test_role_switcher_unknown_role():
    assert client().post("/role", data={"role": "Admin"}).status_code == 400


def test_banner_on_all_pages():
    req = make_request(member_name="BannerUser")
    for path in ("/", "/requests/new"):
        assert "sf-banner.js" in client("Member").get(path).text
    assert "sf-banner.js" in client("Viewer").get(f"/requests/{req['id']}").text
