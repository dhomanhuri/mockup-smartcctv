"""Wires a camera's RTSP URL into MediaMTX so the frontend can watch it as
HLS without the browser ever touching RTSP directly.

MediaMTX exposes a REST control API (default :9997) that lets paths be
registered at runtime — this is what makes "add a camera by IP" actually
produce a watchable stream instead of a static placeholder: as soon as a
camera row is created with an rtsp_url, we ask MediaMTX to pull that RTSP
source on demand under a path named after the camera.
"""

import logging
import os

import requests

logger = logging.getLogger("smart_cctv_ai.streaming")

MEDIAMTX_API_URL = os.getenv("MEDIAMTX_API_URL", "http://mediamtx:9997")


def stream_path_for(camera_id: int) -> str:
    return f"cam-{camera_id}"


def register_pull_path(path_name: str, rtsp_url: str) -> bool:
    try:
        resp = requests.post(
            f"{MEDIAMTX_API_URL}/v3/config/paths/add/{path_name}",
            json={"source": rtsp_url, "sourceOnDemand": True},
            timeout=5,
        )
        if resp.status_code in (200, 201):
            logger.info("registered MediaMTX path '%s' -> %s", path_name, rtsp_url)
            return True
        logger.warning(
            "MediaMTX rejected path '%s' (status %s): %s",
            path_name, resp.status_code, resp.text,
        )
        return False
    except requests.RequestException as exc:
        logger.warning("could not reach MediaMTX to register path '%s': %s", path_name, exc)
        return False


def remove_path(path_name: str) -> None:
    try:
        requests.post(f"{MEDIAMTX_API_URL}/v3/config/paths/delete/{path_name}", timeout=5)
    except requests.RequestException as exc:
        logger.warning("could not remove MediaMTX path '%s': %s", path_name, exc)
