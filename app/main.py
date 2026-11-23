import os
import pathlib

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.loan import ROLES, STATUSES, TOOLS, LoanRequest
from app.service import create_request, decide, get_request, list_requests
from app.store import make_store

BASE = pathlib.Path(__file__).parent
app = FastAPI(title="Makerspace equipment loan requests")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.globals["sf"] = {"expires": os.environ.get("SF_EXPIRES", ""), "env": os.environ.get("SF_ENV", "local")}
templates.env.globals["TOOLS"] = TOOLS
templates.env.globals["ROLES"] = ROLES
store = make_store()


def role_of(request: Request) -> str:
    role = request.cookies.get("role", "Viewer")
    return role if role in ROLES else "Viewer"


def require(role: str):
    def dependency(request: Request) -> str:
        if role_of(request) != role:
            raise HTTPException(403, f"Only a {role} can do this")
        return role

    return dependency


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"


@app.post("/role")
def set_role(role: str = Form(...)):
    if role not in ROLES:
        raise HTTPException(400, "Unknown role")
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("role", role, samesite="lax", httponly=True)
    return resp


@app.get("/")
def index(request: Request, status: str | None = None):
    filters = {"status": status} if status in STATUSES else {}
    rows = list_requests(store, **filters)
    return templates.TemplateResponse(request, "index.html",
                                      {"requests": rows, "role": role_of(request), "status": status,
                                       "statuses": STATUSES, "TOOLS": TOOLS})


@app.get("/requests/new", dependencies=[Depends(require("Member"))])
def new_form(request: Request):
    return templates.TemplateResponse(request, "new.html", {"role": role_of(request)})


@app.post("/requests", dependencies=[Depends(require("Member"))])
def submit(member_name: str = Form(..., max_length=80), tool: str = Form(..., max_length=40),
           start_date: str = Form(..., max_length=10), end_date: str = Form(..., max_length=10),
           reason: str = Form(..., max_length=1000)):
    try:
        payload = LoanRequest(member_name=member_name, tool=tool, start_date=start_date,
                              end_date=end_date, reason=reason)
    except ValidationError as exc:
        raise HTTPException(422, str(exc))
    create_request(store, payload)
    return RedirectResponse("/", status_code=303)


@app.get("/requests/{req_id}")
def detail(request: Request, req_id: str):
    record = get_request(store, req_id)
    if not record:
        raise HTTPException(404, "Request not found")
    return templates.TemplateResponse(request, "detail.html",
                                      {"r": record, "role": role_of(request)})


@app.post("/requests/{req_id}/decision", dependencies=[Depends(require("Approver"))])
def apply_decision(req_id: str, decision: str = Form(...), note: str = Form(..., max_length=500)):
    if decision not in ("Approved", "Rejected"):
        raise HTTPException(400, "Unknown decision")
    try:
        decide(store, req_id, decision, note)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return RedirectResponse("/", status_code=303)
