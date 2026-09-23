"""Object storage for violation snapshot evidence — see ADR-0017.

Replaces the earlier local-disk-volume approach (a plain `/data/snapshots`
directory baked into the backend container) with MinIO, an open-source
S3-compatible object store, so evidence photos survive independently of
any one backend container/volume and could later be fronted by a real
S3-compatible service with zero code changes (same client library, just
different endpoint/credentials).
"""

import io
import logging
import os

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger("smart_cctv_ai.storage")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "snapshots")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)


def ensure_bucket() -> None:
    """Called once on backend startup — idempotent, matches this
    project's existing `_seed_*` pattern for anything that needs to
    exist before the app can serve requests."""
    try:
        if not _client.bucket_exists(MINIO_BUCKET):
            _client.make_bucket(MINIO_BUCKET)
            logger.info("created MinIO bucket %s", MINIO_BUCKET)
    except S3Error as exc:
        logger.error("could not ensure MinIO bucket %s: %s", MINIO_BUCKET, exc)


def put_snapshot(object_name: str, data: bytes, content_type: str = "image/jpeg") -> bool:
    try:
        _client.put_object(
            MINIO_BUCKET, object_name, io.BytesIO(data), length=len(data), content_type=content_type,
        )
        return True
    except S3Error as exc:
        logger.error("failed to upload snapshot %s to MinIO: %s", object_name, exc)
        return False


def get_snapshot(object_name: str) -> bytes | None:
    response = None
    try:
        response = _client.get_object(MINIO_BUCKET, object_name)
        return response.read()
    except S3Error as exc:
        logger.warning("snapshot %s not found in MinIO: %s", object_name, exc)
        return None
    finally:
        if response is not None:
            response.close()
            response.release_conn()
