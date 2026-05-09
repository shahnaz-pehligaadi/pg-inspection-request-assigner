from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PendingRequest(BaseModel):
    """A pending inspection request as returned by Inspection Service.

    Only the fields the optimizer cares about; extras are ignored.
    """

    model_config = {"extra": "ignore"}

    request_id: str = Field(alias="requestId")
    pincode: str
    preferred_time: Optional[datetime] = Field(default=None, alias="preferredTime")
    urgency_level: Optional[str] = Field(default=None, alias="urgencyLevel")
    status: str


class Slot(BaseModel):
    """One slot from the per-pincode availability response."""

    model_config = {"extra": "ignore"}

    slot_time: str = Field(alias="slotTime")
    is_available: bool = Field(default=True, alias="isAvailable")


class InspectorAvailability(BaseModel):
    """An inspector + their open slots for a given (pincode, date)."""

    model_config = {"extra": "ignore"}

    employee_id: str = Field(alias="employeeId")
    inspector_name: Optional[str] = Field(default=None, alias="inspectorName")
    availability_status: str = Field(alias="availabilityStatus")
    slots: list[Slot] = Field(default_factory=list)
    has_empty_slots: bool = Field(default=False, alias="hasEmptySlots")


class BucketKey(BaseModel):
    pincode: str
    date: str  # YYYY-MM-DD


class Assignment(BaseModel):
    request_id: str
    employee_id: str
    slot_time: str
    pincode: str
    date: str


class SkippedRequest(BaseModel):
    request_id: str
    reason: str
    pincode: str
    date: Optional[str] = None


class AutoAssignStats(BaseModel):
    total_pending: int = 0
    buckets: int = 0
    assigned: int = 0
    skipped: int = 0
    elapsed_ms: int = 0


class AutoAssignResponse(BaseModel):
    run_id: str
    dry_run: bool
    assigned: list[Assignment] = Field(default_factory=list)
    skipped: list[SkippedRequest] = Field(default_factory=list)
    stats: AutoAssignStats


class AutoAssignRequest(BaseModel):
    dry_run: Optional[bool] = None
    pincodes: Optional[list[str]] = None
    solver_time_sec: Optional[int] = None
