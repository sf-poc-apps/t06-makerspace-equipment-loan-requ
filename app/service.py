"""Service layer for the makerspace loan workflow."""
from __future__ import annotations

import datetime as dt

from pydantic import ValidationError

from app.loan import LoanRequest
from app.store import MemoryStore

MAX_NOTE = 500


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def create_request(store: MemoryStore, payload: LoanRequest) -> dict:
    doc = store.create("requests", {
        "member_name": payload.member_name.strip(),
        "tool": payload.tool.strip(),
        "start_date": payload.start_date.strip(),
        "end_date": payload.end_date.strip(),
        "reason": payload.reason.strip(),
        "status": "Pending",
        "history": [{
            "status": "Pending",
            "note": "Submitted",
            "role": "Member",
            "timestamp": _now(),
        }],
    })
    return doc


def get_request(store: MemoryStore, req_id: str) -> dict | None:
    return store.get("requests", req_id)


def list_requests(store: MemoryStore, **filters: str) -> list[dict]:
    return store.list("requests", order_by="-created_at", **filters)


def decide(store: MemoryStore, req_id: str, decision: str, note: str) -> dict:
    if decision not in ("Approved", "Rejected"):
        raise ValueError("decision must be Approved or Rejected")
    note = (note or "").strip()
    if not note:
        raise ValueError("A decision note is required")
    if len(note) > MAX_NOTE:
        raise ValueError("Decision note is too long")
    current = store.get("requests", req_id)
    if not current:
        raise LookupError("Request not found")
    if current.get("status") != "Pending":
        raise ValueError("Only pending requests can be decided")
    history = list(current.get("history", []))
    history.append({"status": decision, "note": note, "role": "Approver", "timestamp": _now()})
    return store.update("requests", req_id, {"status": decision, "history": history})