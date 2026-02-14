#!/usr/bin/env python3
"""Issue signed Thermozona Pro license tokens.

Usage guide:
- Set private key via THERMOZONA_LICENSE_PRIVATE_KEY_PEM (inline PEM) or
  THERMOZONA_LICENSE_PRIVATE_KEY_PEM_PATH (path to PEM file).
- Generate one JWT token on stdout for use as `license_key` in configuration.yaml.

Example:
  export THERMOZONA_LICENSE_PRIVATE_KEY_PEM_PATH=/secure/thermozona-private.pem
  python scripts/issue_pro_license.py --sub github:japetheape --days 30 \
    --issuer thermozona --source github_sponsors --tier pro --kid main-2026-01

Security:
- Never commit private keys to git.
- Avoid exposing secrets in shell history or CI logs.
"""
from __future__ import annotations

import argparse
import base64
import importlib
import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Keep these values in sync with `custom_components/thermozona/licensing.py`.
# We intentionally do not import that module here: importing
# `custom_components.thermozona.*` would execute `__init__.py`, which depends
# on Home Assistant.
PRO_LICENSE_SOURCES = {"github_sponsors", "ghs"}
PRO_LICENSE_TIERS = {"pro", "sponsor"}
PRO_LICENSE_DEFAULT_KEY_ID = "main-2026-01"

PRIVATE_KEY_PEM_ENV = "THERMOZONA_LICENSE_PRIVATE_KEY_PEM"
PRIVATE_KEY_PEM_PATH_ENV = "THERMOZONA_LICENSE_PRIVATE_KEY_PEM_PATH"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _load_crypto_modules():
    """Load cryptography modules lazily.

    This keeps the script importable without a configured Python environment,
    while still failing with a clear message when run.
    """

    try:
        serialization = importlib.import_module(
            "cryptography.hazmat.primitives.serialization"
        )
        ed25519 = importlib.import_module(
            "cryptography.hazmat.primitives.asymmetric.ed25519"
        )
    except ModuleNotFoundError as err:
        raise RuntimeError(
            "Missing dependency: cryptography. "
            "Install with: python -m pip install cryptography"
        ) from err

    return serialization, ed25519.Ed25519PrivateKey


def _load_private_key_from_env():
    key_pem = os.getenv(PRIVATE_KEY_PEM_ENV)
    if not key_pem:
        key_path = os.getenv(PRIVATE_KEY_PEM_PATH_ENV)
        if not key_path:
            raise RuntimeError(
                "Missing private key. Set THERMOZONA_LICENSE_PRIVATE_KEY_PEM "
                "or THERMOZONA_LICENSE_PRIVATE_KEY_PEM_PATH"
            )
        key_pem = Path(key_path).read_text(encoding="utf-8")

    serialization, ed25519_private_key_type = _load_crypto_modules()

    key = serialization.load_pem_private_key(key_pem.encode("utf-8"), password=None)
    if not isinstance(key, ed25519_private_key_type):
        raise RuntimeError("Private key must be an Ed25519 key")
    return key


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Issue a Thermozona Pro JWT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Environment:\n"
            "  THERMOZONA_LICENSE_PRIVATE_KEY_PEM       Inline private key PEM\n"
            "  THERMOZONA_LICENSE_PRIVATE_KEY_PEM_PATH  Path to private key PEM\n\n"
            "Example:\n"
            "  python scripts/issue_pro_license.py --sub github:japetheape "
            "--days 30 --issuer thermozona --source github_sponsors "
            "--tier pro --kid main-2026-01"
        ),
    )
    parser.add_argument("--sub", required=True, help="Subject (user/account id)")
    parser.add_argument("--days", type=int, default=30, help="Token lifetime in days")
    parser.add_argument("--issuer", default="thermozona", help="JWT issuer claim")
    parser.add_argument(
        "--kid",
        default=PRO_LICENSE_DEFAULT_KEY_ID,
        help="Key identifier (JWT header kid)",
    )
    parser.add_argument(
        "--source",
        default="github_sponsors",
        choices=sorted(PRO_LICENSE_SOURCES),
        help="License source claim",
    )
    parser.add_argument(
        "--tier",
        default="pro",
        choices=sorted(PRO_LICENSE_TIERS),
        help="License tier claim",
    )
    parser.add_argument(
        "--not-before-minutes",
        type=int,
        default=None,
        help="Optional nbf claim offset in minutes (negative allows slight clock skew)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    subject = args.sub.strip()
    if not subject:
        raise RuntimeError("--sub must not be empty")
    if args.days <= 0:
        raise RuntimeError("--days must be greater than zero")
    if not args.kid.strip():
        raise RuntimeError("--kid must not be empty")

    private_key = _load_private_key_from_env()

    now = int(time.time())
    payload = {
        "iss": args.issuer,
        "sub": subject,
        "src": args.source,
        "tier": args.tier,
        "iat": now,
        "exp": now + int(timedelta(days=args.days).total_seconds()),
    }
    if args.not_before_minutes is not None:
        payload["nbf"] = now + args.not_before_minutes * 60

    header = {"alg": "EdDSA", "typ": "JWT", "kid": args.kid.strip()}
    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = private_key.sign(signing_input)

    token = f"{encoded_header}.{encoded_payload}.{_b64url(signature)}"
    print(token)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as err:
        print(f"Error: {err}", file=sys.stderr)
        raise SystemExit(1)
