#!/usr/bin/env python3
"""Publish Langfuse storage capacity as an OTLP gauge."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


FILESYSTEM_PATH = "/mnt/aorus/langfuse"
OTLP_METRICS_URL = "http://127.0.0.1:4318/v1/metrics"


def main() -> int:
    filesystem = os.statvfs(FILESYSTEM_PATH)
    total = filesystem.f_frsize * filesystem.f_blocks
    free = filesystem.f_frsize * filesystem.f_bavail
    used = total - free
    timestamp = str(time.time_ns())

    def point(state: str, value: int) -> dict[str, object]:
        return {
            "timeUnixNano": timestamp,
            "asInt": str(value),
            "attributes": [
                {"key": "mountpoint", "value": {"stringValue": "/host-data"}},
                {"key": "state", "value": {"stringValue": state}},
            ],
        }

    payload = {
        "resourceMetrics": [{
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "langfuse-disk-metrics"}}]},
            "scopeMetrics": [{
                "scope": {"name": "langfuse-disk-metrics"},
                "metrics": [{
                    "name": "system.filesystem.usage",
                    "unit": "By",
                    "gauge": {"dataPoints": [point("used", used), point("free", free)]},
                }],
            }],
        }],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(OTLP_METRICS_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
    print(json.dumps({"filesystem": "/host-data", "free_bytes": free, "used_bytes": used}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, urllib.error.URLError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
