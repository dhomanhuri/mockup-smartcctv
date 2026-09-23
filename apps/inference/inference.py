"""Real inference worker for Smart CCTV AI.

Replaces the earlier `inference-sim` (random event generator, kept only as
apps/inference-sim/ for reference — see ADR-0010). This worker runs two
small pretrained YOLOv8 models against each camera's live stream (pulled
from MediaMTX over RTSP) and posts a violation event to the backend
whenever a rule fires, through the exact same /api/events contract the
simulator used — nothing downstream (storage, notifications, dashboard,
websocket) had to change to plug real detection in.

Models
------
- APD cameras: `models/hardhat.pt`, a YOLOv8-nano model published on
  Hugging Face as keremberke/yolov8n-hard-hat-detection, fine-tuned on the
  public "Hard Hat Workers" dataset. Classes: Hardhat, NO-Hardhat. Used
  as-is, no further training.
- Vehicle cameras: `models/yolov8n.pt`, Ultralytics' own stock
  COCO-pretrained YOLOv8-nano release. There is no public pretrained class
  for "person riding in a truck bed" specifically, so vehicle violation
  detection is a zone heuristic on top of a real, generic "person"
  detection: a person whose bounding-box centroid falls inside that
  camera's configured cargo-bed zone counts as a violation. A real
  deployment calibrates each camera's zone during commissioning (walk the
  physical bed's corners in the live view); DEFAULT_ZONE below is a
  placeholder covering most of the frame so the demo cameras work without
  per-camera calibration. This is an honest limitation, not a shortcut
  hidden from the rest of the platform — see ADR-0010.

Both models are CPU-sized on purpose (nano variants, ~6MB each) so this
runs without a GPU on the lab host. Expect on the order of 1 processed
frame per camera per SAMPLE_INTERVAL_SECONDS on CPU, not real-time
video-rate — adequate for periodic sampling, not for tight-latency
production use without a GPU (see the HLD's deployment note on this).
"""

import base64
import json
import logging
import os
import threading
import time
from dataclasses import dataclass

import cv2
import requests
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("smart_cctv_ai.inference")

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
MEDIAMTX_RTSP_BASE = os.getenv("MEDIAMTX_RTSP_BASE", "rtsp://mediamtx:8554")

SAMPLE_INTERVAL_SECONDS = float(os.getenv("SAMPLE_INTERVAL_SECONDS", "4"))
COOLDOWN_SECONDS = float(os.getenv("COOLDOWN_SECONDS", "60"))

HARDHAT_CONF_THRESHOLD = float(os.getenv("HARDHAT_CONF_THRESHOLD", "0.45"))
PERSON_CONF_THRESHOLD = float(os.getenv("PERSON_CONF_THRESHOLD", "0.45"))
RULES_CACHE_TTL_SECONDS = 30.0

# Populated from GET /internal/notification-rules (Pengaturan > Aturan
# Notifikasi persists these) and refreshed on this TTL, so lowering a
# category's threshold in the dashboard changes live detection sensitivity
# within RULES_CACHE_TTL_SECONDS — not just a number shown in a form. Falls
# back to the env-var defaults above if the backend call ever fails, so a
# transient network hiccup degrades to "last known good," not "no
# detection at all."
_rules_cache: dict = {"by_category": {}, "fetched_at": 0.0}


def get_min_confidence(category: str, fallback: float) -> float:
    now = time.time()
    if now - _rules_cache["fetched_at"] > RULES_CACHE_TTL_SECONDS:
        try:
            r = requests.get(f"{BACKEND_URL}/internal/notification-rules", timeout=3)
            r.raise_for_status()
            _rules_cache["by_category"] = {row["category"]: row for row in r.json()}
            _rules_cache["fetched_at"] = now
        except requests.RequestException as exc:
            logger.warning("failed to refresh notification rules, keeping last known values: %s", exc)
    rule = _rules_cache["by_category"].get(category)
    return rule["min_confidence"] if rule else fallback

# Normalized (x1, y1, x2, y2) placeholder "cargo bed" zone — most of the
# frame, minus a thin border. Override per camera id via VEHICLE_ZONES_JSON,
# e.g. {"5": [0.1, 0.35, 0.95, 0.95]}.
DEFAULT_ZONE = (0.05, 0.2, 0.95, 0.95)
VEHICLE_ZONES: dict[str, tuple[float, float, float, float]] = {
    k: tuple(v) for k, v in json.loads(os.getenv("VEHICLE_ZONES_JSON", "{}")).items()
}

HARDHAT_MODEL_PATH = os.getenv("HARDHAT_MODEL_PATH", "models/hardhat.pt")
PERSON_MODEL_PATH = os.getenv("PERSON_MODEL_PATH", "models/yolov8n.pt")

# ultralyticsplus published this model with label order [Hardhat, NO-Hardhat]
NO_HARDHAT_CLASS_NAME = "NO-Hardhat"
COCO_PERSON_CLASS_ID = 0  # "person" is always class 0 in stock COCO weights


def wait_for_backend() -> None:
    while True:
        try:
            r = requests.get(f"{BACKEND_URL}/api/health", timeout=3)
            if r.status_code == 200:
                logger.info("backend is up at %s", BACKEND_URL)
                return
        except requests.RequestException:
            pass
        logger.info("waiting for backend at %s ...", BACKEND_URL)
        time.sleep(2)


def fetch_cameras() -> list[dict]:
    while True:
        try:
            r = requests.get(f"{BACKEND_URL}/internal/cameras", timeout=5)
            r.raise_for_status()
            cameras = [c for c in r.json() if c.get("stream_path")]
            if cameras:
                return cameras
        except requests.RequestException as exc:
            logger.warning("failed to fetch cameras: %s", exc)
        logger.info("no cameras with a live stream_path yet, retrying...")
        time.sleep(3)


def submit_event(camera_id: int, violation_type: str, confidence: float, frame) -> None:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    snapshot_b64 = base64.b64encode(buf.tobytes()).decode("ascii") if ok else None
    try:
        r = requests.post(
            f"{BACKEND_URL}/api/events",
            json={
                "camera_id": camera_id,
                "type": violation_type,
                "confidence": round(confidence, 4),
                "snapshot_base64": snapshot_b64,
            },
            timeout=10,
        )
        r.raise_for_status()
    except requests.RequestException as exc:
        logger.error("failed to submit event for camera %s: %s", camera_id, exc)


# How many consecutive "no frame" reads (not exceptions — cv2.VideoCapture
# doesn't raise when a stream just stops producing frames, it silently
# keeps returning (False, None) forever) before forcing a reconnect. At
# the default 4s SAMPLE_INTERVAL_SECONDS this is ~20s — long enough to
# ride out a brief hiccup, short enough that a demo-camera restart (its
# RTSP publish momentarily disappearing) doesn't leave a camera stuck
# silently dead until someone notices and restarts this container by
# hand, which is exactly what happened the first time this was hit.
MAX_CONSECUTIVE_FAILURES = 5


@dataclass
class CameraState:
    camera: dict
    cap: "cv2.VideoCapture"
    last_alert_at: float = 0.0
    consecutive_failures: int = 0


def open_capture(stream_path: str) -> "cv2.VideoCapture":
    url = f"{MEDIAMTX_RTSP_BASE}/{stream_path}"
    cap = cv2.VideoCapture(url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def run_apd_camera(state: CameraState, model: YOLO) -> bool:
    """Returns whether a frame was actually read — camera_worker uses
    this to decide when to force a reconnect (see MAX_CONSECUTIVE_FAILURES)."""
    camera = state.camera
    ok, frame = state.cap.read()
    if not ok or frame is None:
        logger.warning("[%s] no frame available yet", camera["name"])
        return False

    threshold = get_min_confidence("apd", HARDHAT_CONF_THRESHOLD)
    results = model.predict(frame, verbose=False, conf=threshold)[0]
    names = results.names
    best_conf = 0.0
    for box in results.boxes:
        cls_name = names[int(box.cls[0])]
        conf = float(box.conf[0])
        if cls_name == NO_HARDHAT_CLASS_NAME and conf > best_conf:
            best_conf = conf

    if best_conf <= 0.0:
        return True
    if time.time() - state.last_alert_at < COOLDOWN_SECONDS:
        return True

    logger.info("[%s] NO-Hardhat detected (confidence %.0f%%) -> emitting event", camera["name"], best_conf * 100)
    submit_event(camera["id"], "no_helmet", best_conf, frame)
    state.last_alert_at = time.time()
    return True


def run_vehicle_camera(state: CameraState, model: YOLO) -> bool:
    """Returns whether a frame was actually read — see run_apd_camera."""
    camera = state.camera
    ok, frame = state.cap.read()
    if not ok or frame is None:
        logger.warning("[%s] no frame available yet", camera["name"])
        return False

    h, w = frame.shape[:2]
    zx1, zy1, zx2, zy2 = VEHICLE_ZONES.get(str(camera["id"]), DEFAULT_ZONE)
    zone_px = (zx1 * w, zy1 * h, zx2 * w, zy2 * h)

    threshold = get_min_confidence("vehicle", PERSON_CONF_THRESHOLD)
    results = model.predict(frame, verbose=False, conf=threshold, classes=[COCO_PERSON_CLASS_ID])[0]
    best_conf = 0.0
    for box in results.boxes:
        conf = float(box.conf[0])
        bx1, by1, bx2, by2 = [float(v) for v in box.xyxy[0]]
        cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
        if zone_px[0] <= cx <= zone_px[2] and zone_px[1] <= cy <= zone_px[3] and conf > best_conf:
            best_conf = conf

    if best_conf <= 0.0:
        return True
    if time.time() - state.last_alert_at < COOLDOWN_SECONDS:
        return True

    logger.info("[%s] person in cargo zone (confidence %.0f%%) -> emitting event", camera["name"], best_conf * 100)
    submit_event(camera["id"], "truck_bed_rider", best_conf, frame)
    state.last_alert_at = time.time()
    return True


def camera_worker(camera: dict, hardhat_model: YOLO, person_model: YOLO) -> None:
    state = CameraState(camera=camera, cap=open_capture(camera["stream_path"]))
    logger.info(
        "[%s] worker started (category=%s, stream=%s)",
        camera["name"], camera["category"], camera["stream_path"],
    )
    is_apd = camera["category"] == "apd"

    while True:
        try:
            got_frame = run_apd_camera(state, hardhat_model) if is_apd else run_vehicle_camera(state, person_model)
            if got_frame:
                state.consecutive_failures = 0
            else:
                state.consecutive_failures += 1
                if state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.warning(
                        "[%s] no frame for %d consecutive attempts, reconnecting",
                        camera["name"], state.consecutive_failures,
                    )
                    state.cap.release()
                    state.cap = open_capture(camera["stream_path"])
                    state.consecutive_failures = 0
        except Exception:
            logger.exception("[%s] detection cycle failed", camera["name"])
            state.cap.release()
            state.cap = open_capture(camera["stream_path"])
            state.consecutive_failures = 0
        time.sleep(SAMPLE_INTERVAL_SECONDS)


def main() -> None:
    wait_for_backend()
    logger.info("loading models (hardhat=%s, person=%s) ...", HARDHAT_MODEL_PATH, PERSON_MODEL_PATH)
    hardhat_model = YOLO(HARDHAT_MODEL_PATH)
    person_model = YOLO(PERSON_MODEL_PATH)
    logger.info("models loaded")

    cameras = fetch_cameras()
    logger.info("starting real inference for %d camera(s)", len(cameras))

    threads = [
        threading.Thread(target=camera_worker, args=(camera, hardhat_model, person_model), daemon=True)
        for camera in cameras
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
