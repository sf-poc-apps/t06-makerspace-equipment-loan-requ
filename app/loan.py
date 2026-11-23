"""Domain types and validation for the makerspace equipment loan workflow."""
from __future__ import annotations

import datetime as dt
import re

from pydantic import BaseModel, field_validator

TOOLS = ["3D Printer", "Laser Cutter", "CNC Router", "Soldering Station", "Sewing Machine"]
STATUSES = ("Pending", "Approved", "Rejected")
ROLES = ("Member", "Approver", "Viewer")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class LoanRequest(BaseModel):
    member_name: str
    tool: str
    start_date: str
    end_date: str
    reason: str

    @field_validator("member_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("member_name is required")
        if len(v) > 80:
            raise ValueError("member_name is too long")
        return v

    @field_validator("tool")
    @classmethod
    def _tool(cls, v: str) -> str:
        v = v.strip()
        if v not in TOOLS:
            raise ValueError("tool must be one of the fixed tools")
        return v

    @field_validator("start_date", "end_date")
    @classmethod
    def _date(cls, v: str) -> str:
        v = v.strip()
        if not DATE_RE.match(v):
            raise ValueError("date must be an ISO date (YYYY-MM-DD)")
        try:
            dt.date.fromisoformat(v)
        except ValueError:
            raise ValueError("date must be a valid ISO date (YYYY-MM-DD)")
        return v

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("reason is required")
        if len(v) > 1000:
            raise ValueError("reason is too long")
        return v