"""Keycloak-backed request authentication.

Every protected endpoint expects `Authorization: Bearer <access_token>`
issued by the Keycloak realm configured via env vars. The token's signature
is verified against the realm's JWKS (fetched from Keycloak over the
internal docker network and cached for a few minutes); the issuer claim is
checked against the externally-visible Keycloak URL, since that is what
Keycloak actually stamps into tokens it issues to the browser.
"""

import os
import time

import requests
from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

KEYCLOAK_INTERNAL_URL = os.getenv("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080/auth")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "smart-cctv-ai")
KEYCLOAK_ISSUER = os.getenv(
    "KEYCLOAK_ISSUER", "http://localhost/auth/realms/smart-cctv-ai"
)

JWKS_URL = f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
_JWKS_TTL_SECONDS = 300

_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}


def _get_jwks() -> dict:
    now = time.time()
    if _jwks_cache["keys"] is None or now - _jwks_cache["fetched_at"] > _JWKS_TTL_SECONDS:
        resp = requests.get(JWKS_URL, timeout=5)
        resp.raise_for_status()
        _jwks_cache["keys"] = resp.json()
        _jwks_cache["fetched_at"] = now
    return _jwks_cache["keys"]


def verify_token(token: str) -> dict:
    jwks = _get_jwks()
    return jwt.decode(
        token,
        jwks,
        algorithms=["RS256"],
        issuer=KEYCLOAK_ISSUER,
        options={"verify_aud": False},
    )


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1]
    try:
        return verify_token(token)
    except (JWTError, requests.RequestException) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def user_roles(user: dict) -> set[str]:
    return set(user.get("realm_access", {}).get("roles", []))


def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    if "admin" not in user_roles(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requires the 'admin' realm role",
        )
    return user


def get_current_manager(user: dict = Depends(get_current_user)) -> dict:
    """Case management actions (assign, close, change camera/notification
    config) — anything the platform's RBAC matrix reserves for Supervisor
    or Admin, never plain Operator. See ADR-0011."""
    if not user_roles(user) & {"admin", "supervisor"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requires the 'admin' or 'supervisor' realm role",
        )
    return user
