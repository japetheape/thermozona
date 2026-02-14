#!/usr/bin/env python3
"""Verify Thermozona Pro license tokens."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from custom_components.thermozona.licensing import validate_pro_license_key


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a Thermozona Pro JWT")
    parser.add_argument("token", help="JWT to verify")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = validate_pro_license_key(args.token)
    if result.is_valid:
        print("valid")
        return 0

    print(f"invalid: {result.reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
