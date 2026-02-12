"""License utilities for Thermozona tier gating."""
from __future__ import annotations

import base64
import json
import time

PRO_LICENSE_ISSUERS = {"thermozona", "thermozona.appventures.nl"}
PRO_LICENSE_SOURCES = {"github_sponsors", "ghs"}


def normalize_license_key(license_key: str | None) -> str:
    """Return normalized license key representation for validation."""
    if license_key is None:
        return ""
    normalized = license_key.strip()
    if "." in normalized:
        return normalized
    return normalized.upper()


def is_pro_license_key(license_key: str | None) -> bool:
    """Return True when the key is a valid GitHub sponsor token."""
    normalized = normalize_license_key(license_key)
    return is_github_sponsor_token(normalized)


def is_github_sponsor_token(license_key: str | None) -> bool:
    """Return True when key is a valid (unexpired) GitHub sponsor token."""
    normalized = normalize_license_key(license_key)
    payload = _decode_jwt_payload(normalized)
    if payload is None:
        return False

    issuer = payload.get("iss")
    subject = payload.get("sub")
    source = payload.get("src")
    tier = payload.get("tier")

    if issuer not in PRO_LICENSE_ISSUERS:
        return False
    if not isinstance(subject, str) or not subject.strip():
        return False
    if source not in PRO_LICENSE_SOURCES:
        return False
    if tier not in {"pro", "sponsor"}:
        return False

    if not _is_payload_in_valid_time_window(payload):
        return False

    return True


def _decode_jwt_payload(token: str) -> dict | None:
    """Decode JWT payload without signature verification."""
    parts = token.split(".")
    if len(parts) != 3:
        return None

    payload_segment = parts[1]
    padded = payload_segment + "=" * ((4 - len(payload_segment) % 4) % 4)
    try:
        raw_payload = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return None

    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def _is_payload_in_valid_time_window(payload: dict) -> bool:
    """Validate exp/nbf/iat claims against current UTC timestamp."""
    now = int(time.time())

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= now:
        return False

    nbf = payload.get("nbf")
    if nbf is not None:
        if not isinstance(nbf, int) or nbf > now:
            return False

    iat = payload.get("iat")
    if iat is not None:
        if not isinstance(iat, int) or iat > now:
            return False

    return True
