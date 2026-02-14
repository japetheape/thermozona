#!/usr/bin/env python3
"""Issue signed Thermozona Pro license tokens."""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from custom_components.thermozona.licensing import PRO_LICENSE_SOURCES
from custom_components.thermozona.licensing import PRO_LICENSE_DEFAULT_KEY_ID
from custom_components.thermozona.licensing import PRO_LICENSE_TIERS

PRIVATE_KEY_PEM_ENV = "THERMOZONA_LICENSE_PRIVATE_KEY_PEM"
PRIVATE_KEY_PEM_PATH_ENV = "THERMOZONA_LICENSE_PRIVATE_KEY_PEM_PATH"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _load_private_key_from_env() -> Ed25519PrivateKey:
    key_pem = os.getenv(PRIVATE_KEY_PEM_ENV)
    if not key_pem:
        key_path = os.getenv(PRIVATE_KEY_PEM_PATH_ENV)
        if not key_path:
            raise RuntimeError(
                "Missing private key. Set THERMOZONA_LICENSE_PRIVATE_KEY_PEM "
                "or THERMOZONA_LICENSE_PRIVATE_KEY_PEM_PATH"
            )
        key_pem = Path(key_path).read_text(encoding="utf-8")

    key = serialization.load_pem_private_key(key_pem.encode("utf-8"), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimeError("Private key must be an Ed25519 key")
    return key


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Issue a Thermozona Pro JWT")
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
