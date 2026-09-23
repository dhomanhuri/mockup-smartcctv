from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .models import CameraCategory, ViolationStatus, ViolationType


class CameraCreate(BaseModel):
    name: str
    ip_address: str
    location: Optional[str] = None
    category: CameraCategory = CameraCategory.apd
    rtsp_url: Optional[str] = None


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    category: Optional[CameraCategory] = None
    rtsp_url: Optional[str] = None
    clear_rtsp_url: bool = False


class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ip_address: str
    location: Optional[str]
    status: str
    category: CameraCategory
    rtsp_url: Optional[str]
    stream_path: Optional[str]
    created_at: datetime


class EventIn(BaseModel):
    camera_id: int
    type: ViolationType
    confidence: float
    # Base64-encoded JPEG the inference worker captured at the moment of
    # detection. Optional so the ingest endpoint stays usable by anything
    # that can't produce a frame (e.g. a manual test POST).
    snapshot_base64: Optional[str] = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author: str
    text: str
    created_at: datetime


class NoteCreate(BaseModel):
    text: str


class ViolationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: int
    camera_name: Optional[str] = None
    camera_location: Optional[str] = None
    type: ViolationType
    label: str
    category: str
    severity: str
    confidence: float
    has_snapshot: bool = False
    acknowledged: bool
    is_case: bool
    status: ViolationStatus
    assigned_to: Optional[str]
    created_at: datetime


class ViolationDetailOut(ViolationOut):
    notes: list[NoteOut] = []


class ViolationStatusUpdate(BaseModel):
    status: ViolationStatus


class ViolationAssignUpdate(BaseModel):
    assigned_to: Optional[str] = None


class ViolationCaseUpdate(BaseModel):
    is_case: bool


class AdminUserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: str
    temporary_password: bool = True
    role: str = "operator"


class AssignableUserOut(BaseModel):
    username: str
    name: str


class StatsOut(BaseModel):
    total_cameras: int
    online_cameras: int
    total_violations: int
    unacknowledged: int
    open_cases: int
    last_24h: int
    by_type: dict[str, int]


class NotificationRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str
    min_confidence: float
    escalate_after_minutes: int
    escalate_enabled: bool
    email_enabled: bool


class NotificationRuleUpdate(BaseModel):
    min_confidence: Optional[float] = None
    escalate_after_minutes: Optional[int] = None
    escalate_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None


class ReportScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    frequency_days: int
    recipient_email: Optional[str]
    last_sent_at: Optional[datetime]


class ReportScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    frequency_days: Optional[int] = None
    recipient_email: Optional[str] = None


class CameraDayCount(BaseModel):
    camera_id: int
    camera_name: str
    location: Optional[str]
    category: str
    count: int


class DailyCount(BaseModel):
    date: str
    apd: int
    vehicle: int


class ReportSummaryOut(BaseModel):
    # Explicit date range this summary covers (ADR-0017) — inclusive on
    # both ends, replaces the earlier "last N days from now" model so a
    # report can be regenerated for the exact same period later.
    start: str
    end: str
    days: int
    # Alert-level (every AI detection, is_case or not) — the volume/trend
    # numbers: "how much is happening".
    total: int
    apd_total: int
    vehicle_total: int
    avg_per_day: float
    daily: list[DailyCount]
    by_camera: list[CameraDayCount]
    # Case-level (only alerts a human promoted — ADR-0012) — the workflow
    # numbers: "how well are we handling what we chose to track". Empty/
    # None-safe when nothing has been promoted yet.
    case_total: int
    completed_count: int
    completion_rate: float
    avg_response_minutes: Optional[float]
