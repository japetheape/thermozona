"""Bootstrap Home Assistant onboarding with a local test user."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


HA_URL = _env("HA_URL", "http://homeassistant:8123").rstrip("/")
HA_CLIENT_ID = _env("HA_CLIENT_ID", "http://localhost:8123/")
HA_REDIRECT_URI = _env("HA_REDIRECT_URI", "http://localhost:8123/")
HA_TEST_USER_NAME = _env("HA_TEST_USER_NAME", "Test User")
HA_TEST_USER_USERNAME = _env("HA_TEST_USER_USERNAME", "test")
HA_TEST_USER_PASSWORD = _env("HA_TEST_USER_PASSWORD", "test12345")
HA_TEST_USER_LANGUAGE = _env("HA_TEST_USER_LANGUAGE", "en")
HA_LOCATION_NAME = _env("HA_LOCATION_NAME", "Thermozona Test Home")
HA_LATITUDE = float(_env("HA_LATITUDE", "52.3676"))
HA_LONGITUDE = float(_env("HA_LONGITUDE", "4.9041"))
HA_ELEVATION = int(_env("HA_ELEVATION", "0"))
HA_UNIT_SYSTEM = _env("HA_UNIT_SYSTEM", "metric")
HA_TIME_ZONE = _env("HA_TIME_ZONE", "Europe/Amsterdam")
HA_CURRENCY = _env("HA_CURRENCY", "EUR")


def _request_json(
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
    token: str | None = None,
    form: dict[str, str] | None = None,
) -> dict[str, object] | list[object]:
    headers = {"Accept": "application/json"}

    if form is not None:
        body = urllib.parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    else:
        body = None

    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        f"{HA_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read().decode("utf-8").strip()
        if not raw:
            return {}
        return json.loads(raw)


def _wait_for_onboarding(timeout_seconds: int = 300) -> list[dict[str, object]]:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""

    while time.monotonic() < deadline:
        try:
            data = _request_json("GET", "/api/onboarding")
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            last_error = str(err)

        time.sleep(2)

    raise RuntimeError(f"Timed out waiting for Home Assistant onboarding API: {last_error}")


def _step_done(steps: list[dict[str, object]], name: str) -> bool:
    for step in steps:
        if step.get("step") == name:
            return bool(step.get("done"))
    return False


def main() -> None:
    print("Waiting for Home Assistant onboarding API...")
    steps = _wait_for_onboarding()

    if _step_done(steps, "user"):
        print("Onboarding already completed. Nothing to do.")
        return

    print("Creating test user...")
    user_data = _request_json(
        "POST",
        "/api/onboarding/users",
        payload={
            "name": HA_TEST_USER_NAME,
            "username": HA_TEST_USER_USERNAME,
            "password": HA_TEST_USER_PASSWORD,
            "language": HA_TEST_USER_LANGUAGE,
            "client_id": HA_CLIENT_ID,
        },
    )

    if not isinstance(user_data, dict) or "auth_code" not in user_data:
        raise RuntimeError("Home Assistant onboarding did not return an auth_code")

    token_data = _request_json(
        "POST",
        "/auth/token",
        form={
            "grant_type": "authorization_code",
            "code": str(user_data["auth_code"]),
            "client_id": HA_CLIENT_ID,
        },
    )

    access_token = ""
    if isinstance(token_data, dict):
        access_token = str(token_data.get("access_token", ""))
    if not access_token:
        raise RuntimeError("Failed to exchange auth code for access token")

    print("Applying core configuration...")
    _request_json(
        "POST",
        "/api/onboarding/core_config",
        token=access_token,
        payload={
            "location_name": HA_LOCATION_NAME,
            "latitude": HA_LATITUDE,
            "longitude": HA_LONGITUDE,
            "elevation": HA_ELEVATION,
            "unit_system": HA_UNIT_SYSTEM,
            "time_zone": HA_TIME_ZONE,
            "currency": HA_CURRENCY,
        },
    )

    print("Disabling analytics sharing by default...")
    _request_json(
        "POST",
        "/api/onboarding/analytics",
        token=access_token,
        payload={
            "preferences": {
                "base": False,
                "diagnostics": False,
                "statistics": False,
                "usage": False,
            }
        },
    )

    print("Completing integration onboarding step...")
    _request_json(
        "POST",
        "/api/onboarding/integration",
        token=access_token,
        payload={
            "client_id": HA_CLIENT_ID,
            "redirect_uri": HA_REDIRECT_URI,
        },
    )

    print("Home Assistant onboarding complete. Test user is ready.")


if __name__ == "__main__":
    main()
