import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from .database import Base


class ViolationType(str, enum.Enum):
    no_helmet = "no_helmet"
    truck_bed_rider = "truck_bed_rider"


class CameraCategory(str, enum.Enum):
    apd = "apd"
    vehicle = "vehicle"


class Severity(str, enum.Enum):
    warning = "warning"
    critical = "critical"


class ViolationStatus(str, enum.Enum):
    baru = "baru"
    diproses = "diproses"
    selesai = "selesai"


VIOLATION_META = {
    ViolationType.no_helmet: {
        "label": "Tidak Menggunakan Helm",
        "category": "apd",
        "severity": Severity.warning,
    },
    ViolationType.truck_bed_rider: {
        "label": "Penumpang di Bak Kendaraan",
        "category": "vehicle",
        "severity": Severity.critical,
    },
}


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ip_address = Column(String, unique=True, nullable=False, index=True)
    location = Column(String, nullable=True)
    status = Column(String, default="online", nullable=False)
    category = Column(Enum(CameraCategory), nullable=False, server_default=CameraCategory.apd.value)
    rtsp_url = Column(String, nullable=True)
    stream_path = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    violations = relationship("Violation", back_populates="camera")


class Violation(Base):
    __tablename__ = "violations"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    type = Column(Enum(ViolationType), nullable=False)
    label = Column(String, nullable=False)
    category = Column(String, nullable=False)
    severity = Column(Enum(Severity), nullable=False)
    confidence = Column(Float, nullable=False)
    snapshot_ref = Column(String, nullable=True)
    # Every AI detection lands here as a plain alert (is_case=False) —
    # visible in APD/Vehicle Detection's "Riwayat Pelanggaran" log, but
    # NOT in Case Violation. A human explicitly promotes one into a case
    # (POST .../promote) when it actually warrants tracking; that's the
    # only thing that makes it show up on the Case Violation page and
    # unlocks status/assign/notes. See ADR-0012 — a prior version of this
    # made every single detection an automatic "case", flooding that page
    # with near-duplicate entries every detection cycle.
    is_case = Column(Boolean, default=False, nullable=False)
    # `acknowledged` predates `status` (see ADR-0011) and is kept in sync
    # with it for backward compatibility — true whenever status != 'baru'.
    acknowledged = Column(Boolean, default=False, nullable=False)
    status = Column(Enum(ViolationStatus), nullable=False, server_default=ViolationStatus.baru.value)
    assigned_to = Column(String, nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    # First time status moved away from 'baru' — the "response time" the
    # Laporan & Analitik page reports on. Deliberately not "time to
    # close": that's a different (also useful, not built) metric.
    responded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    camera = relationship("Camera", back_populates="violations")
    notes = relationship(
        "ViolationNote", back_populates="violation",
        order_by="ViolationNote.created_at", cascade="all, delete-orphan",
    )

    @property
    def has_snapshot(self) -> bool:
        return bool(self.snapshot_ref)

    @property
    def camera_name(self) -> str | None:
        return self.camera.name if self.camera else None

    @property
    def camera_location(self) -> str | None:
        return self.camera.location if self.camera else None


class ViolationNote(Base):
    __tablename__ = "violation_notes"

    id = Column(Integer, primary_key=True, index=True)
    violation_id = Column(Integer, ForeignKey("violations.id"), nullable=False)
    author = Column(String, nullable=False)
    text = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    violation = relationship("Violation", back_populates="notes")


class NotificationRule(Base):
    """One row per camera category — see ADR-0011. `apps/inference` polls
    `min_confidence` from here (cached briefly) so changing it in the
    Pengaturan > Aturan Notifikasi tab actually changes live detection
    sensitivity, not just a display value. `escalate_after_minutes` /
    `escalate_enabled` are read by `_periodic_escalation_check` in
    main.py — the escalation email itself is real; there is no per-role
    email routing yet, so it lands in the same NOTIFY_EMAIL_TO inbox with
    a distinct subject, honestly short of "page the on-call supervisor"."""

    __tablename__ = "notification_rules"

    category = Column(String, primary_key=True)  # "apd" | "vehicle"
    min_confidence = Column(Float, nullable=False)
    escalate_after_minutes = Column(Integer, nullable=False)
    escalate_enabled = Column(Boolean, nullable=False, default=True)
    email_enabled = Column(Boolean, nullable=False, default=True)
    # ADR-0014 briefly added a `weekly_target` compliance-target column
    # here, then ADR-0016 dropped the whole concept after the demo made
    # clear an arbitrary made-up target just made every category read as
    # "MELEBIHI TARGET" with no real baseline behind it. The column may
    # still physically exist on an already-migrated database (this
    # project only ever adds columns, never drops them) — it's simply
    # unmapped and unused now.


class ReportSchedule(Base):
    """Singleton (id=1) config for the "Recurring Report" — a periodic
    email (see `_periodic_recurring_report_check` in main.py) sent
    without anyone having to compile it by hand. See ADR-0014."""

    __tablename__ = "report_schedule"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    frequency_days = Column(Integer, nullable=False, default=7)
    recipient_email = Column(String, nullable=True)  # falls back to NOTIFY_EMAIL_TO if unset
    last_sent_at = Column(DateTime(timezone=True), nullable=True)
