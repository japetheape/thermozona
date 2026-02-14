#!/usr/bin/env python3
"""Verify Thermozona Pro license tokens."""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_licensing_module():
    """Load licensing module without importing Home Assistant."""

    licensing_path = PROJECT_ROOT / "custom_components" / "thermozona" / "licensing.py"
    if not licensing_path.exists():
        raise RuntimeError(f"Unable to locate licensing module at {licensing_path}")

    module_name = "thermozona_licensing"
    spec = importlib.util.spec_from_file_location(module_name, str(licensing_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load licensing module from {licensing_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as err:
        if err.name == "cryptography":
            raise RuntimeError(
                "Missing dependency: cryptography. "
                "Install with: python -m pip install cryptography"
            ) from err
        raise
    return module


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a Thermozona Pro JWT")
    parser.add_argument("token", help="JWT to verify")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    licensing = _load_licensing_module()
    validate_pro_license_key = licensing.validate_pro_license_key
    result = validate_pro_license_key(args.token)
    if result.is_valid:
        print("valid")
        return 0

    print(f"invalid: {result.reason}")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as err:
        print(f"Error: {err}", file=sys.stderr)
        raise SystemExit(1)
