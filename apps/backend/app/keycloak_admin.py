"""Backend-only helper for the Admin Dashboard: creates/lists/enables users
in the app's Keycloak realm (name configurable via KEYCLOAK_REALM — see
ADR-0016) using Keycloak's Admin REST API.

Deliberately does NOT reuse the logged-in admin's own browser token for
these calls. Instead it authenticates as a dedicated confidential
service-account client (KC_USER_MANAGER_CLIENT_ID, never exposed to the
browser) via the client_credentials grant. This keeps the privileged
Keycloak Admin API credential server-side only — the human admin's token
just has to prove (via the "admin" realm role, checked in auth.py) that
they're allowed to trigger these backend calls.
"""

import os
import time

import requests

KEYCLOAK_INTERNAL_URL = os.getenv("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080/auth")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "smart-cctv-ai")
KC_USER_MANAGER_CLIENT_ID = os.getenv("KC_USER_MANAGER_CLIENT_ID", "smart-cctv-ai-user-manager")
KC_USER_MANAGER_SECRET = os.getenv("KC_USER_MANAGER_SECRET", "")

TOKEN_URL = f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
ADMIN_BASE = f"{KEYCLOAK_INTERNAL_URL}/admin/realms/{KEYCLOAK_REALM}"

_token_cache: dict = {"access_token": None, "expires_at": 0.0}


def _service_account_token() -> str:
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 10:
        return _token_cache["access_token"]

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": KC_USER_MANAGER_CLIENT_ID,
            "client_secret": KC_USER_MANAGER_SECRET,
        },
        timeout=5,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = now + data["expires_in"]
    return data["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_service_account_token()}"}


def list_users() -> list[dict]:
    resp = requests.get(f"{ADMIN_BASE}/users", headers=_headers(), params={"max": 200}, timeout=5)
    resp.raise_for_status()
    users = resp.json()

    for user in users:
        roles_resp = requests.get(
            f"{ADMIN_BASE}/users/{user['id']}/role-mappings/realm", headers=_headers(), timeout=5
        )
        user["realmRoles"] = [r["name"] for r in roles_resp.json()] if roles_resp.ok else []
    return users


def _get_realm_role(role_name: str) -> dict:
    resp = requests.get(f"{ADMIN_BASE}/roles/{role_name}", headers=_headers(), timeout=5)
    resp.raise_for_status()
    return resp.json()


def create_user(username: str, email: str | None, first_name: str | None, last_name: str | None,
                 password: str, temporary_password: bool, role: str) -> str:
    headers = _headers()
    body = {
        "username": username,
        "email": email,
        "firstName": first_name,
        "lastName": last_name,
        "enabled": True,
        "emailVerified": bool(email),
        "credentials": [{"type": "password", "value": password, "temporary": temporary_password}],
    }
    resp = requests.post(f"{ADMIN_BASE}/users", json=body, headers=headers, timeout=5)
    if resp.status_code == 409:
        raise ValueError("username sudah terdaftar")
    resp.raise_for_status()

    user_id = resp.headers["Location"].rstrip("/").split("/")[-1]

    role_repr = _get_realm_role(role)
    requests.post(
        f"{ADMIN_BASE}/users/{user_id}/role-mappings/realm",
        json=[role_repr],
        headers=headers,
        timeout=5,
    )
    return user_id


def set_user_enabled(user_id: str, enabled: bool) -> None:
    resp = requests.put(
        f"{ADMIN_BASE}/users/{user_id}", json={"enabled": enabled}, headers=_headers(), timeout=5
    )
    resp.raise_for_status()
