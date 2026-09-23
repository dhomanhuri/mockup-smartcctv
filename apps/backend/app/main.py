import asyncio
import base64
import binascii
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

import requests
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import func, text
from sqlalchemy.orm import Session, joinedload

from . import keycloak_admin, models, schemas, storage
from .auth import get_current_admin, get_current_manager, get_current_user, user_roles, verify_token
from .database import Base, SessionLocal, engine, get_db, wait_for_db
from .models import VIOLATION_META
from .notifications import send_escalation, send_notification, send_recurring_report
from .pdf_report import build_report_pdf
from .streaming import register_pull_path, remove_path, stream_path_for
from .ws_manager import manager

logger = logging.getLogger("smart_cctv_ai.backend")

DEFAULT_NOTIFICATION_RULES = {
    # min_confidence matches what apps/inference actually uses by default
    # (see its HARDHAT_CONF_THRESHOLD/PERSON_CONF_THRESHOLD) rather than an
    # arbitrary "enterprise-looking" number, so this setting is truthful
    # about what it controls the moment it's first read — see ADR-0011.
    "apd": {"min_confidence": 0.45, "escalate_after_minutes": 30, "escalate_enabled": True, "email_enabled": True},
    "vehicle": {"min_confidence": 0.45, "escalate_after_minutes": 45, "escalate_enabled": True, "email_enabled": True},
}

app = FastAPI(title="Smart CCTV AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    wait_for_db()
    Base.metadata.create_all(bind=engine)
    _run_schema_migrations()
    storage.ensure_bucket()
    _seed_demo_cameras()
    _backfill_demo_camera_data()
    _seed_notification_rules()
    _seed_report_schedule()
    _reregister_camera_streams()
    asyncio.create_task(_periodic_stream_resync())
    asyncio.create_task(_periodic_escalation_check())
    asyncio.create_task(_periodic_recurring_report_check())


def _run_schema_migrations() -> None:
    """`Base.metadata.create_all` only creates tables that don't exist yet —
    it never alters an existing one. Columns added to a model after its
    table already existed in a prior deploy need an explicit, idempotent
    ALTER here so upgrading in place doesn't require dropping the postgres
    volume. New tables (violation_notes, notification_rules) don't need an
    entry here — create_all handles those on its own."""
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS category "
            "VARCHAR NOT NULL DEFAULT 'apd'"
        ))
        conn.execute(text(
            "ALTER TABLE violations ADD COLUMN IF NOT EXISTS status "
            "VARCHAR NOT NULL DEFAULT 'baru'"
        ))
        conn.execute(text(
            "ALTER TABLE violations ADD COLUMN IF NOT EXISTS is_case "
            "BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        conn.execute(text(
            "ALTER TABLE violations ADD COLUMN IF NOT EXISTS assigned_to VARCHAR"
        ))
        conn.execute(text(
            "ALTER TABLE violations ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ"
        ))
        conn.execute(text(
            "ALTER TABLE violations ADD COLUMN IF NOT EXISTS responded_at TIMESTAMPTZ"
        ))
        # Violation.category predates the "APD" branding and used to store
        # "safety" — unify it with Camera.category now that both exist.
        conn.execute(text(
            "UPDATE violations SET category = 'apd' WHERE category = 'safety'"
        ))
        # Backfill status from the older acknowledged flag for any row that
        # predates the `status` column, so existing "already handled" rows
        # don't all reappear as brand new "Baru" cases.
        conn.execute(text(
            "UPDATE violations SET status = 'diproses' "
            "WHERE acknowledged = TRUE AND status = 'baru'"
        ))


async def _periodic_stream_resync() -> None:
    """MediaMTX keeps registered RTSP pull paths in memory only — if it
    restarts independently of the backend (e.g. a container-level restart,
    not a full stack redeploy), every dynamically-added camera would lose
    its stream until someone re-saves it. Re-asserting periodically closes
    that gap without needing MediaMTX itself to persist any state."""
    while True:
        await asyncio.sleep(300)
        _reregister_camera_streams()


async def _periodic_escalation_check() -> None:
    """Real, but honestly limited: there is no per-role email directory
    yet, so "escalate to Supervisor" still lands in NOTIFY_EMAIL_TO — see
    notifications.send_escalation and ADR-0011."""
    while True:
        await asyncio.sleep(60)
        _run_escalation_check()


def _run_escalation_check() -> None:
    db = SessionLocal()
    try:
        rules = {r.category: r for r in db.query(models.NotificationRule).all()}
        pending = (
            db.query(models.Violation)
            .filter(models.Violation.status == models.ViolationStatus.baru)
            .filter(models.Violation.escalated_at.is_(None))
            .all()
        )
        now = datetime.now(timezone.utc)
        for violation in pending:
            rule = rules.get(violation.category)
            if not rule or not rule.escalate_enabled:
                continue
            age_minutes = (now - violation.created_at).total_seconds() / 60
            if age_minutes < rule.escalate_after_minutes:
                continue
            camera = db.query(models.Camera).get(violation.camera_id)
            if not camera:
                continue
            if rule.email_enabled:
                send_escalation(violation, camera, "supervisor", rule.escalate_after_minutes)
            violation.escalated_at = now
            db.commit()
    finally:
        db.close()


async def _periodic_recurring_report_check() -> None:
    """"Recurring Report" (ADR-0014) — checked every 10 minutes so the
    actual send happens close to when `frequency_days` elapses, without
    needing a real cron/scheduler service in this deploy."""
    while True:
        await asyncio.sleep(600)
        _run_recurring_report_check()


def _run_recurring_report_check() -> None:
    db = SessionLocal()
    try:
        schedule = db.query(models.ReportSchedule).get(1)
        if not schedule or not schedule.enabled:
            return
        now = datetime.now(timezone.utc)
        if schedule.last_sent_at is not None:
            due_at = schedule.last_sent_at + timedelta(days=schedule.frequency_days)
            if now < due_at:
                return
        end_date = now.date()
        start_date = end_date - timedelta(days=min(schedule.frequency_days, MAX_REPORT_RANGE_DAYS) - 1)
        summary = _compute_report_summary(db, start_date, end_date)
        recipient = schedule.recipient_email or None
        pdf_bytes = build_report_pdf("executive", summary)
        send_recurring_report(summary, schedule.frequency_days, recipient, pdf_bytes=pdf_bytes)
        schedule.last_sent_at = now
        db.commit()
    finally:
        db.close()


def _reregister_camera_streams() -> None:
    db = SessionLocal()
    try:
        cameras = db.query(models.Camera).filter(models.Camera.rtsp_url.isnot(None)).all()
        for camera in cameras:
            path_name = stream_path_for(camera.id)
            if register_pull_path(path_name, camera.rtsp_url) and camera.stream_path != path_name:
                camera.stream_path = path_name
        db.commit()
    finally:
        db.close()


def _backfill_demo_camera_data() -> None:
    """`_seed_demo_cameras` only inserts a row when its IP isn't already
    taken, so a camera seeded before `category` and the real demo-camera
    stream_paths existed would otherwise sit forever with the ALTER's blanket
    'apd' default and no stream. Keyed on the fixed 192.168.56.10x demo IPs
    only — never touches a camera a real admin has actually added — this
    just re-asserts the correct demo values every startup, which is what
    lets this upgrade land without dropping the postgres volume."""
    corrections = {
        "192.168.56.101": ("apd", "demo-gerbang"),
        "192.168.56.102": ("apd", "demo-produksi"),
        "192.168.56.105": ("apd", "demo-workshop"),
        "192.168.56.103": ("vehicle", "demo-jalur"),
        "192.168.56.104": ("vehicle", "demo-parkiran"),
    }
    db = SessionLocal()
    try:
        for ip, (category, stream_path) in corrections.items():
            camera = db.query(models.Camera).filter_by(ip_address=ip).first()
            if camera and (camera.category != category or camera.stream_path != stream_path):
                camera.category = category
                camera.stream_path = stream_path
        db.commit()
    finally:
        db.close()


def _seed_demo_cameras() -> None:
    # stream_path here points at a `demo-camera` container publishing
    # directly into MediaMTX under that static path (see
    # infra/demo-camera/) — not a `rtsp_url` MediaMTX would need to pull
    # from, so no register_pull_path() call is needed for these.
    demo_cameras = [
        ("Gerbang Utama", "192.168.56.101", "Pos Satpam Depan", "apd", "demo-gerbang"),
        ("Area Produksi 1", "192.168.56.102", "Lantai Produksi - Zona A", "apd", "demo-produksi"),
        ("Workshop", "192.168.56.105", "Bengkel Perawatan", "apd", "demo-workshop"),
        ("Jalur Kendaraan", "192.168.56.103", "Jalan Akses Loading Dock", "vehicle", "demo-jalur"),
        ("Parkiran Truk", "192.168.56.104", "Area Parkir Kendaraan Berat", "vehicle", "demo-parkiran"),
    ]
    db = SessionLocal()
    try:
        existing = {c.ip_address for c in db.query(models.Camera).all()}
        for name, ip, location, category, stream_path in demo_cameras:
            if ip in existing:
                continue
            db.add(
                models.Camera(
                    name=name,
                    ip_address=ip,
                    location=location,
                    category=category,
                    stream_path=stream_path,
                )
            )
        db.commit()
    finally:
        db.close()


def _seed_notification_rules() -> None:
    db = SessionLocal()
    try:
        existing = {r.category for r in db.query(models.NotificationRule).all()}
        for category, defaults in DEFAULT_NOTIFICATION_RULES.items():
            if category in existing:
                continue
            db.add(models.NotificationRule(category=category, **defaults))
        db.commit()
    finally:
        db.close()


def _seed_report_schedule() -> None:
    db = SessionLocal()
    try:
        if not db.query(models.ReportSchedule).get(1):
            db.add(models.ReportSchedule(id=1, enabled=True, frequency_days=7, recipient_email=None))
            db.commit()
    finally:
        db.close()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/cameras", response_model=list[schemas.CameraOut])
def list_cameras(db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    return db.query(models.Camera).order_by(models.Camera.id).all()


@app.post("/api/cameras", response_model=schemas.CameraOut)
def create_camera(
    payload: schemas.CameraCreate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    if db.query(models.Camera).filter_by(ip_address=payload.ip_address).first():
        raise HTTPException(status_code=409, detail="camera with this IP already registered")

    camera = models.Camera(**payload.model_dump())
    db.add(camera)
    db.commit()
    db.refresh(camera)

    if camera.rtsp_url:
        path_name = stream_path_for(camera.id)
        if register_pull_path(path_name, camera.rtsp_url):
            camera.stream_path = path_name
            db.commit()
            db.refresh(camera)

    return camera


@app.get("/api/cameras/{camera_id}", response_model=schemas.CameraOut)
def get_camera(camera_id: int, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    camera = db.query(models.Camera).get(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="camera not found")
    return camera


@app.put("/api/cameras/{camera_id}", response_model=schemas.CameraOut)
def update_camera(
    camera_id: int,
    payload: schemas.CameraUpdate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    camera = db.query(models.Camera).get(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="camera not found")

    if payload.name is not None:
        camera.name = payload.name
    if payload.location is not None:
        camera.location = payload.location
    if payload.category is not None:
        camera.category = payload.category

    rtsp_changed = False
    if payload.clear_rtsp_url:
        rtsp_changed = camera.rtsp_url is not None
        camera.rtsp_url = None
    elif payload.rtsp_url is not None and payload.rtsp_url != camera.rtsp_url:
        camera.rtsp_url = payload.rtsp_url
        rtsp_changed = True

    if rtsp_changed:
        if camera.stream_path and camera.stream_path.startswith("cam-"):
            remove_path(camera.stream_path)
            camera.stream_path = None
        if camera.rtsp_url:
            path_name = stream_path_for(camera.id)
            if register_pull_path(path_name, camera.rtsp_url):
                camera.stream_path = path_name

    db.commit()
    db.refresh(camera)
    return camera


@app.delete("/api/cameras/{camera_id}", status_code=204)
def delete_camera(camera_id: int, db: Session = Depends(get_db), _admin: dict = Depends(get_current_admin)):
    camera = db.query(models.Camera).get(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="camera not found")

    if camera.stream_path and camera.stream_path.startswith("cam-"):
        remove_path(camera.stream_path)

    db.query(models.Violation).filter(models.Violation.camera_id == camera_id).delete()
    db.delete(camera)
    db.commit()
    return None


@app.get("/api/violations", response_model=list[schemas.ViolationOut])
def list_violations(
    type: str | None = None,
    category: str | None = None,
    status: str | None = None,
    camera_id: int | None = None,
    is_case: bool | None = None,
    only_unacknowledged: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Every AI detection lands here as a plain alert — `is_case=true`
    scopes this down to the ones a human has explicitly promoted (see
    ADR-0012). APD/Vehicle Detection's "Riwayat Pelanggaran" calls this
    without `is_case` (the full alert log); Case Violation always passes
    `is_case=true`."""
    query = db.query(models.Violation).options(joinedload(models.Violation.camera))
    if type:
        query = query.filter(models.Violation.type == type)
    if category:
        query = query.filter(models.Violation.category == category)
    if status:
        query = query.filter(models.Violation.status == status)
    if camera_id:
        query = query.filter(models.Violation.camera_id == camera_id)
    if is_case is not None:
        query = query.filter(models.Violation.is_case.is_(is_case))
    if only_unacknowledged:
        query = query.filter(models.Violation.acknowledged.is_(False))
    return query.order_by(models.Violation.created_at.desc()).limit(limit).all()


@app.get("/api/violations/{violation_id}", response_model=schemas.ViolationDetailOut)
def get_violation(violation_id: int, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    violation = (
        db.query(models.Violation)
        .options(joinedload(models.Violation.camera), joinedload(models.Violation.notes))
        .get(violation_id)
    )
    if not violation:
        raise HTTPException(status_code=404, detail="violation not found")
    return violation


def _mark_responded_if_needed(violation: models.Violation) -> None:
    if violation.responded_at is None and violation.status != models.ViolationStatus.baru:
        violation.responded_at = datetime.now(timezone.utc)


@app.put("/api/violations/{violation_id}/status", response_model=schemas.ViolationOut)
def set_violation_status(
    violation_id: int,
    payload: schemas.ViolationStatusUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Any authenticated user can move Baru -> Diproses (acknowledge); only
    Supervisor/Admin can move a case to Selesai — see ADR-0011's RBAC
    matrix. Enforced here, not just hidden in the UI."""
    violation = db.query(models.Violation).get(violation_id)
    if not violation:
        raise HTTPException(status_code=404, detail="violation not found")

    if payload.status == models.ViolationStatus.selesai and not user_roles(user) & {"admin", "supervisor"}:
        raise HTTPException(status_code=403, detail="only Supervisor/Admin can close a case")

    violation.status = payload.status
    violation.acknowledged = payload.status != models.ViolationStatus.baru
    _mark_responded_if_needed(violation)
    db.commit()
    db.refresh(violation)
    return violation


@app.post("/api/violations/{violation_id}/ack", response_model=schemas.ViolationOut)
def acknowledge_violation(
    violation_id: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Kept for backward compatibility — equivalent to setting status to
    'diproses'."""
    violation = db.query(models.Violation).get(violation_id)
    if not violation:
        raise HTTPException(status_code=404, detail="violation not found")
    violation.acknowledged = True
    if violation.status == models.ViolationStatus.baru:
        violation.status = models.ViolationStatus.diproses
    _mark_responded_if_needed(violation)
    db.commit()
    db.refresh(violation)
    return violation


@app.put("/api/violations/{violation_id}/case", response_model=schemas.ViolationOut)
def set_violation_case(
    violation_id: int,
    payload: schemas.ViolationCaseUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Promote a plain alert into a tracked case (`is_case: true`) or
    un-promote one made by mistake (`is_case: false`) — any authenticated
    user, deliberately not manager-only: this is "flag it for tracking",
    not "assign/close it" (those stay Supervisor/Admin, see
    set_violation_status/assign_violation). Un-promoting does not delete
    anything — the underlying detection stays in the alert log either
    way, it just stops showing on the Case Violation page. See ADR-0012."""
    violation = db.query(models.Violation).get(violation_id)
    if not violation:
        raise HTTPException(status_code=404, detail="violation not found")
    violation.is_case = payload.is_case
    db.commit()
    db.refresh(violation)
    return violation


@app.put("/api/violations/{violation_id}/assign", response_model=schemas.ViolationOut)
def assign_violation(
    violation_id: int,
    payload: schemas.ViolationAssignUpdate,
    db: Session = Depends(get_db),
    _manager: dict = Depends(get_current_manager),
):
    violation = db.query(models.Violation).get(violation_id)
    if not violation:
        raise HTTPException(status_code=404, detail="violation not found")
    violation.assigned_to = payload.assigned_to
    db.commit()
    db.refresh(violation)
    return violation


@app.get("/api/users/operators", response_model=list[schemas.AssignableUserOut])
def list_assignable_operators(_manager: dict = Depends(get_current_manager)):
    """Backs the "Ditugaskan ke" dropdown in case-modal.js — real
    operator accounts from Keycloak (User Management), not a hardcoded
    placeholder list. Supervisor/Admin-only, matching who can actually
    assign a case (assign_violation above). Scoped to the "operator"
    role specifically: a case gets assigned to whoever does the
    fieldwork, not to another supervisor/admin."""
    try:
        users = keycloak_admin.list_users()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"could not reach Keycloak: {exc}") from exc
    operators = []
    for u in users:
        roles = u.get("realmRoles", [])
        # `admin` also carries the `operator` role for its own UI access
        # (ADR-0011) — excluded here so the admin account never shows up
        # as an assignable field operator; a "pure" operator only.
        if not u.get("enabled") or "operator" not in roles or "admin" in roles or "supervisor" in roles:
            continue
        name = f"{u.get('firstName', '')} {u.get('lastName', '')}".strip() or u["username"]
        operators.append(schemas.AssignableUserOut(username=u["username"], name=name))
    return operators


@app.post("/api/violations/{violation_id}/notes", response_model=schemas.NoteOut)
def add_violation_note(
    violation_id: int,
    payload: schemas.NoteCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    violation = db.query(models.Violation).get(violation_id)
    if not violation:
        raise HTTPException(status_code=404, detail="violation not found")
    author = user.get("name") or user.get("preferred_username") or "Unknown"
    note = models.ViolationNote(violation_id=violation_id, author=author, text=payload.text)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


MAX_REPORT_RANGE_DAYS = 31


def _resolve_report_range(start: str | None, end: str | None) -> tuple[date, date]:
    """Shared parsing/validation for every endpoint that takes a report
    date range (ADR-0017) — defaults to the last 7 days when omitted,
    always inclusive on both ends, capped at MAX_REPORT_RANGE_DAYS so a
    report/export/email can't be asked to crunch an unbounded window."""
    today = datetime.now(timezone.utc).date()
    end_date = date.fromisoformat(end) if end else today
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=6)
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start date must not be after end date")
    if (end_date - start_date).days + 1 > MAX_REPORT_RANGE_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"date range too wide — maximum {MAX_REPORT_RANGE_DAYS} days",
        )
    return start_date, end_date


def _compute_report_summary(db: Session, start_date: date, end_date: date) -> schemas.ReportSummaryOut:
    """Shared by GET /api/reports/summary, the PDF export endpoint, and
    the recurring-report email (ADR-0014/0017) — one computation, three
    consumers, so the dashboard/report/email numbers can never drift
    apart from each other. `start_date`/`end_date` are both inclusive,
    UTC calendar dates."""
    since = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    until = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
    num_days = (end_date - start_date).days + 1
    rows = (
        db.query(models.Violation)
        .filter(models.Violation.created_at >= since, models.Violation.created_at <= until)
        .all()
    )

    total = len(rows)
    apd_total = sum(1 for r in rows if r.category == "apd")
    vehicle_total = sum(1 for r in rows if r.category == "vehicle")

    # Case-level metrics (ADR-0012) — scoped to what a human actually
    # promoted, since status/response-time is only meaningful there.
    cases = [r for r in rows if r.is_case]
    case_total = len(cases)
    completed = [r for r in cases if r.status == models.ViolationStatus.selesai]
    responded = [r for r in cases if r.responded_at is not None]
    avg_response_minutes = (
        sum((r.responded_at - r.created_at).total_seconds() for r in responded) / len(responded) / 60
        if responded else None
    )

    # Every day in the selected range gets an entry, zero-filled — an
    # explicitly-chosen range benefits from a continuous trend line more
    # than the old "N days back from now" model did.
    daily_map: dict[str, dict[str, int]] = {
        (start_date + timedelta(days=i)).isoformat(): {"apd": 0, "vehicle": 0}
        for i in range(num_days)
    }
    for r in rows:
        bucket = daily_map[r.created_at.date().isoformat()]
        bucket[r.category if r.category in bucket else "apd"] += 1
    daily = [
        schemas.DailyCount(date=day, apd=counts["apd"], vehicle=counts["vehicle"])
        for day, counts in sorted(daily_map.items())
    ]

    camera_counts: dict[int, int] = {}
    for r in rows:
        camera_counts[r.camera_id] = camera_counts.get(r.camera_id, 0) + 1
    cameras = {c.id: c for c in db.query(models.Camera).all()}
    by_camera = sorted(
        (
            schemas.CameraDayCount(
                camera_id=cid,
                camera_name=cameras[cid].name if cid in cameras else f"Kamera #{cid}",
                location=cameras[cid].location if cid in cameras else None,
                category=cameras[cid].category.value if cid in cameras else "apd",
                count=count,
            )
            for cid, count in camera_counts.items()
        ),
        key=lambda c: c.count,
        reverse=True,
    )

    return schemas.ReportSummaryOut(
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        days=num_days,
        total=total,
        apd_total=apd_total,
        vehicle_total=vehicle_total,
        avg_per_day=round(total / num_days, 1) if num_days else 0.0,
        case_total=case_total,
        completed_count=len(completed),
        completion_rate=round(len(completed) / case_total, 3) if case_total else 0.0,
        avg_response_minutes=round(avg_response_minutes, 1) if avg_response_minutes is not None else None,
        daily=daily,
        by_camera=by_camera,
    )


@app.get("/api/reports/summary", response_model=schemas.ReportSummaryOut)
def report_summary(
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    start_date, end_date = _resolve_report_range(start, end)
    return _compute_report_summary(db, start_date, end_date)


@app.get("/api/report-schedule", response_model=schemas.ReportScheduleOut)
def get_report_schedule(db: Session = Depends(get_db), _admin: dict = Depends(get_current_admin)):
    schedule = db.query(models.ReportSchedule).get(1)
    if not schedule:
        raise HTTPException(status_code=404, detail="report schedule not seeded")
    return schedule


@app.put("/api/report-schedule", response_model=schemas.ReportScheduleOut)
def update_report_schedule(
    payload: schemas.ReportScheduleUpdate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    schedule = db.query(models.ReportSchedule).get(1)
    if not schedule:
        raise HTTPException(status_code=404, detail="report schedule not seeded")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    db.commit()
    db.refresh(schedule)
    return schedule


@app.post("/api/report-schedule/send-now", response_model=schemas.ReportScheduleOut)
def send_report_now(db: Session = Depends(get_db), _admin: dict = Depends(get_current_admin)):
    """Manual "Kirim Sekarang" trigger — lets a demo or a real admin prove
    the Recurring Report actually fires, instead of waiting out
    `frequency_days`. Ignores whether one is already due; still updates
    `last_sent_at` so the automatic schedule doesn't immediately re-fire
    right after."""
    schedule = db.query(models.ReportSchedule).get(1)
    if not schedule:
        raise HTTPException(status_code=404, detail="report schedule not seeded")
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=min(schedule.frequency_days or 7, MAX_REPORT_RANGE_DAYS) - 1)
    summary = _compute_report_summary(db, start_date, end_date)
    pdf_bytes = build_report_pdf("executive", summary)
    send_recurring_report(summary, schedule.frequency_days, schedule.recipient_email or None, pdf_bytes=pdf_bytes)
    schedule.last_sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(schedule)
    return schedule


MAX_EXPORT_DETAIL_ROWS = 500


@app.get("/api/reports/export")
def export_report(
    kind: str = "detail",
    start: str | None = None,
    end: str | None = None,
    token: str | None = None,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """PDF export ("Unduh Laporan") — see ADR-0015/0017. `kind=executive`
    gives a branded, chart-and-table KPI summary a manager can forward
    as-is; `kind=detail` gives that plus the full violation table and an
    embedded photo-evidence gallery (pulled from MinIO — ADR-0017) — a
    comprehensive report, not a bare spreadsheet. `start`/`end` are
    inclusive ISO dates (YYYY-MM-DD), capped at MAX_REPORT_RANGE_DAYS
    apart, defaulting to the last 7 days. Accepts `?token=` alongside the
    Authorization header, matching the snapshot endpoint's pattern, so a
    plain `<a href>` download link (which can't attach a header) still
    works."""
    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1]
    elif token:
        bearer = token
    if not bearer:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        verify_token(bearer)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc

    kind = "executive" if kind == "executive" else "detail"
    start_date, end_date = _resolve_report_range(start, end)
    summary = _compute_report_summary(db, start_date, end_date)
    violations = None
    if kind == "detail":
        since = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        until = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
        violations = (
            db.query(models.Violation)
            .filter(models.Violation.created_at >= since, models.Violation.created_at <= until)
            .order_by(models.Violation.created_at.desc())
            .limit(MAX_EXPORT_DETAIL_ROWS)
            .all()
        )

    pdf_bytes = build_report_pdf(kind, summary, violations=violations)
    filename = f"laporan-{'eksekutif' if kind == 'executive' else 'detail'}-{start_date.isoformat()}_{end_date.isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/notification-rules", response_model=list[schemas.NotificationRuleOut])
def list_notification_rules(db: Session = Depends(get_db), _admin: dict = Depends(get_current_admin)):
    return db.query(models.NotificationRule).order_by(models.NotificationRule.category).all()


@app.put("/api/notification-rules/{category}", response_model=schemas.NotificationRuleOut)
def update_notification_rule(
    category: str,
    payload: schemas.NotificationRuleUpdate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    rule = db.query(models.NotificationRule).get(category)
    if not rule:
        raise HTTPException(status_code=404, detail="unknown category")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@app.get("/internal/cameras", response_model=list[schemas.CameraOut])
def list_cameras_internal(db: Session = Depends(get_db)):
    """Unprotected camera listing for trusted internal callers
    (apps/inference) — mirrors /api/cameras but skips user auth since it's
    never reached through the public reverse proxy, only over the
    docker-internal network."""
    return db.query(models.Camera).order_by(models.Camera.id).all()


@app.get("/internal/notification-rules", response_model=list[schemas.NotificationRuleOut])
def list_notification_rules_internal(db: Session = Depends(get_db)):
    """Unprotected mirror of /api/notification-rules for apps/inference to
    poll its confidence threshold from — same internal-network-only
    reasoning as /internal/cameras."""
    return db.query(models.NotificationRule).all()


def _save_snapshot(violation_id: int, raw: bytes) -> str | None:
    """Uploads to MinIO (ADR-0017) and returns the object key to store as
    `Violation.snapshot_ref` — or None if the upload failed, in which
    case the violation is kept without photo evidence rather than
    failing the whole ingest."""
    object_name = f"{violation_id}-{uuid.uuid4().hex[:8]}.jpg"
    return object_name if storage.put_snapshot(object_name, raw) else None


@app.post("/api/events", response_model=schemas.ViolationOut)
async def ingest_event(payload: schemas.EventIn, db: Session = Depends(get_db)):
    """Entry point the inference worker posts detected violations to.
    Called only from inside the docker network by trusted internal
    services, so it intentionally does not require a user bearer token — a
    real deployment would put a service-account client credentials check
    here instead."""
    camera = db.query(models.Camera).get(payload.camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="camera not found")

    meta = VIOLATION_META[payload.type]
    violation = models.Violation(
        camera_id=camera.id,
        type=payload.type,
        label=meta["label"],
        category=meta["category"],
        severity=meta["severity"],
        confidence=payload.confidence,
    )
    db.add(violation)
    db.commit()
    db.refresh(violation)

    snapshot_bytes = None
    if payload.snapshot_base64:
        try:
            snapshot_bytes = base64.b64decode(payload.snapshot_base64, validate=True)
        except (binascii.Error, ValueError):
            logger.warning("event for violation %s had unparseable snapshot_base64, dropping it", violation.id)
            snapshot_bytes = None
        if snapshot_bytes:
            snapshot_ref = _save_snapshot(violation.id, snapshot_bytes)
            if snapshot_ref:
                violation.snapshot_ref = snapshot_ref
                db.commit()
                db.refresh(violation)

    # "Direct Notify" (ADR-0014) — attach the same snapshot bytes just
    # saved to disk, so the HSSE channel gets photo evidence inline
    # instead of having to log in and open the case to see it.
    send_notification(violation, camera, snapshot_bytes)

    await manager.broadcast(
        {
            "event": "violation",
            "id": violation.id,
            "camera_id": camera.id,
            "camera_name": camera.name,
            "type": violation.type.value,
            "label": violation.label,
            "category": violation.category,
            "severity": violation.severity.value,
            "confidence": violation.confidence,
            "has_snapshot": violation.has_snapshot,
            "created_at": violation.created_at.isoformat() if violation.created_at else None,
        }
    )
    return violation


@app.get("/api/violations/{violation_id}/snapshot")
def get_violation_snapshot(
    violation_id: int,
    token: str | None = None,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """A plain `<img src="...">` can't attach an Authorization header —
    the same constraint /ws/live has — so this accepts a bearer token via
    `?token=` too, not just the header every other endpoint requires.
    Without this, case-modal.js's snapshot <img> always 401s and shows a
    broken-image icon; it was never actually authenticated correctly."""
    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1]
    elif token:
        bearer = token
    if not bearer:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        verify_token(bearer)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc

    violation = db.query(models.Violation).get(violation_id)
    if not violation or not violation.snapshot_ref:
        raise HTTPException(status_code=404, detail="no snapshot for this violation")
    data = storage.get_snapshot(violation.snapshot_ref)
    if data is None:
        raise HTTPException(status_code=404, detail="snapshot missing from object storage")
    return Response(content=data, media_type="image/jpeg")


@app.get("/api/admin/users")
def admin_list_users(_admin: dict = Depends(get_current_admin)):
    return keycloak_admin.list_users()


@app.post("/api/admin/users")
def admin_create_user(payload: schemas.AdminUserCreate, _admin: dict = Depends(get_current_admin)):
    try:
        user_id = keycloak_admin.create_user(
            username=payload.username,
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            password=payload.password,
            temporary_password=payload.temporary_password,
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": user_id}


@app.put("/api/admin/users/{user_id}/enabled")
def admin_set_user_enabled(user_id: str, enabled: bool, _admin: dict = Depends(get_current_admin)):
    keycloak_admin.set_user_enabled(user_id, enabled)
    return {"ok": True}


@app.get("/api/stats", response_model=schemas.StatsOut)
def stats(db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    total_cameras = db.query(models.Camera).count()
    online_cameras = db.query(models.Camera).filter_by(status="online").count()
    total_violations = db.query(models.Violation).count()
    unacknowledged = db.query(models.Violation).filter_by(acknowledged=False).count()
    open_cases = (
        db.query(models.Violation)
        .filter(models.Violation.is_case.is_(True))
        .filter(models.Violation.status != models.ViolationStatus.selesai)
        .count()
    )
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    last_24h = db.query(models.Violation).filter(models.Violation.created_at >= since).count()
    by_type_rows = (
        db.query(models.Violation.type, func.count(models.Violation.id))
        .group_by(models.Violation.type)
        .all()
    )
    by_type = {t.value: count for t, count in by_type_rows}
    return schemas.StatsOut(
        total_cameras=total_cameras,
        online_cameras=online_cameras,
        total_violations=total_violations,
        unacknowledged=unacknowledged,
        open_cases=open_cases,
        last_24h=last_24h,
        by_type=by_type,
    )


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """Browsers can't attach an Authorization header to a WebSocket
    handshake, so the access token is passed as a query param instead and
    verified the same way as the REST endpoints."""
    token = websocket.query_params.get("token")
    try:
        if not token:
            raise ValueError("missing token")
        verify_token(token)
    except Exception:
        await websocket.close(code=4401)
        return

    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
