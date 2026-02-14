"""License utilities for Thermozona tier gating."""
from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PRO_LICENSE_ISSUERS = {"thermozona", "thermozona.appventures.nl"}
PRO_LICENSE_SOURCES = {"github_sponsors", "ghs"}
PRO_LICENSE_TIERS = {"pro", "sponsor"}

PRO_LICENSE_DEFAULT_KEY_ID = "main-2026-01"

# This key is part of Pro-license verification integrity (see NOTICE and
# LICENSE-COMMERCIAL.md for tampering restrictions under commercial terms).
PRO_LICENSE_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEALt8+/pQOfUQRN3Sugun636DwGzabBdPCJ/D82Q8/oiI=
-----END PUBLIC KEY-----"""
PRO_LICENSE_PUBLIC_KEY_PEM_ENV = "THERMOZONA_LICENSE_PUBLIC_KEY_PEM"
PRO_LICENSE_PUBLIC_KEYS_JSON_ENV = "THERMOZONA_LICENSE_PUBLIC_KEYS_JSON"


@dataclass(frozen=True)
class LicenseValidationResult:
    """Structured result of Pro license validation."""

    is_valid: bool
    reason: str


def normalize_license_key(license_key: str | None) -> str:
    """Return normalized license key representation for validation."""
    if license_key is None:
        return ""
    normalized = license_key.strip()
    if "." in normalized:
        return normalized
    return normalized.upper()


def is_pro_license_key(license_key: str | None) -> bool:
    """Return True when the key is a valid Pro license token."""
    return validate_pro_license_key(license_key).is_valid


def is_github_sponsor_token(license_key: str | None) -> bool:
    """Backward-compatible alias for Pro license validation."""
    return validate_pro_license_key(license_key).is_valid


def validate_pro_license_key(license_key: str | None) -> LicenseValidationResult:
    """Validate a Pro license JWT with signature and claim checks."""
    normalized = normalize_license_key(license_key)
    if not normalized:
        return LicenseValidationResult(False, "missing_token")

    decoded = _decode_jwt(normalized)
    if decoded is None:
        return LicenseValidationResult(False, "malformed_token")

    header, payload, signing_input, signature = decoded

    if header.get("alg") != "EdDSA":
        return LicenseValidationResult(False, "unsupported_alg")

    key_id = header.get("kid")
    if key_id is not None and (not isinstance(key_id, str) or not key_id.strip()):
        return LicenseValidationResult(False, "invalid_kid")

    public_keys = _load_public_keys()
    if public_keys is None:
        return LicenseValidationResult(False, "public_key_load_failed")

    if isinstance(key_id, str):
        public_key = public_keys.get(key_id)
        if public_key is None:
            return LicenseValidationResult(False, "unknown_kid")
    else:
        public_key = public_keys.get(PRO_LICENSE_DEFAULT_KEY_ID)
        if public_key is None and len(public_keys) == 1:
            public_key = next(iter(public_keys.values()))
        if public_key is None:
            return LicenseValidationResult(False, "unknown_kid")

    try:
        public_key.verify(signature, signing_input)
    except InvalidSignature:
        return LicenseValidationResult(False, "invalid_signature")

    issuer = payload.get("iss")
    subject = payload.get("sub")
    source = payload.get("src")
    tier = payload.get("tier")

    if issuer not in PRO_LICENSE_ISSUERS:
        return LicenseValidationResult(False, "invalid_issuer")
    if not isinstance(subject, str) or not subject.strip():
        return LicenseValidationResult(False, "invalid_subject")
    if source not in PRO_LICENSE_SOURCES:
        return LicenseValidationResult(False, "invalid_source")
    if tier not in PRO_LICENSE_TIERS:
        return LicenseValidationResult(False, "invalid_tier")

    time_window_reason = _validate_payload_time_window(payload)
    if time_window_reason is not None:
        return LicenseValidationResult(False, time_window_reason)

    return LicenseValidationResult(True, "ok")


def _decode_jwt(token: str) -> tuple[dict, dict, bytes, bytes] | None:
    """Decode a JWT into header/payload/signature parts."""
    parts = token.split(".")
    if len(parts) != 3:
        return None

    try:
        raw_header = _decode_base64url(parts[0])
        raw_payload = _decode_base64url(parts[1])
        signature = _decode_base64url(parts[2])
    except ValueError:
        return None

    try:
        header = json.loads(raw_header.decode("utf-8"))
        payload = json.loads(raw_payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if not isinstance(header, dict):
        return None
    if not isinstance(payload, dict):
        return None

    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    return header, payload, signing_input, signature


def _decode_base64url(value: str) -> bytes:
    """Decode a base64url segment."""
    padded = value + "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as err:
        raise ValueError("invalid base64url") from err


def _load_public_keys() -> dict[str, Ed25519PublicKey] | None:
    """Load configured keyring used for Pro license verification."""
    json_keys = os.getenv(PRO_LICENSE_PUBLIC_KEYS_JSON_ENV)
    if json_keys:
        try:
            parsed = json.loads(json_keys)
        except json.JSONDecodeError:
            return None

        if not isinstance(parsed, dict):
            return None

        keys: dict[str, Ed25519PublicKey] = {}
        for key_id, key_pem in parsed.items():
            if not isinstance(key_id, str) or not key_id.strip():
                return None
            if not isinstance(key_pem, str) or not key_pem.strip():
                return None
            public_key = _load_single_public_key(key_pem)
            if public_key is None:
                return None
            keys[key_id] = public_key

        if not keys:
            return None
        return keys

    public_pem = os.getenv(PRO_LICENSE_PUBLIC_KEY_PEM_ENV, PRO_LICENSE_PUBLIC_KEY_PEM)
    public_key = _load_single_public_key(public_pem)
    if public_key is None:
        return None
    return {PRO_LICENSE_DEFAULT_KEY_ID: public_key}


def _load_single_public_key(public_pem: str) -> Ed25519PublicKey | None:
    """Load one PEM public key as Ed25519."""
    try:
        key = serialization.load_pem_public_key(public_pem.encode("utf-8"))
    except (TypeError, ValueError):
        return None

    if not isinstance(key, Ed25519PublicKey):
        return None
    return key


def _validate_payload_time_window(payload: dict) -> str | None:
    """Validate exp/nbf/iat claims against current UTC timestamp."""
    now = int(time.time())

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= now:
        return "token_expired"

    nbf = payload.get("nbf")
    if nbf is not None:
        if not isinstance(nbf, int) or nbf > now:
            return "token_not_yet_valid"

    iat = payload.get("iat")
    if iat is not None:
        if not isinstance(iat, int) or iat > now:
            return "token_issued_in_future"

    return None
