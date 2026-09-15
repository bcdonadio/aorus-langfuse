#!/usr/bin/env python3
"""Send and verify full-fidelity synthetic OTLP telemetry.

The only host-published endpoint required by this script is the Collector's
OTLP/HTTP receiver. Queries run through Node.js in the Langfuse web container,
which can resolve the private service aliases. Request headers, including
credentials, are passed over stdin and never appear in process arguments.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def request_json(
    url: str,
    *,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10,
) -> Any:
    body = None if data is None else json.dumps(data, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=body, headers=headers or {})
    if body is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


NODE_REQUEST = r"""
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', async () => {
  try {
    const request = JSON.parse(input);
    const response = await fetch(request.url, {headers: request.headers || {}});
    const text = await response.text();
    process.stdout.write(JSON.stringify({status: response.status, body: text}));
  } catch (error) {
    process.stderr.write(String(error));
    process.exitCode = 2;
  }
});
"""


def container_request_json(container: str, url: str, headers: dict[str, str] | None = None) -> Any:
    result = subprocess.run(
        ["podman", "exec", "-i", container, "node", "-e", NODE_REQUEST],
        check=True,
        capture_output=True,
        text=True,
        input=json.dumps({"url": url, "headers": headers or {}}, separators=(",", ":")),
        timeout=10,
    )
    envelope = json.loads(result.stdout)
    status = int(envelope["status"])
    if status < 200 or status >= 300:
        raise urllib.error.HTTPError(url, status, envelope["body"], {}, None)
    return json.loads(envelope["body"]) if envelope["body"] else {}


def post_otlp(collector: str, signal: str, payload: dict[str, Any]) -> None:
    request_json(f"{collector.rstrip('/')}/v1/{signal}", data=payload)


def credentials(path: Path) -> tuple[str, str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    public = document.get("langfuse_public_key") or document.get("public_key") or document.get("publicKey") or document.get("LANGFUSE_PUBLIC_KEY")
    secret = document.get("langfuse_secret_key") or document.get("secret_key") or document.get("secretKey") or document.get("LANGFUSE_SECRET_KEY")
    if not isinstance(public, str) or not isinstance(secret, str):
        raise ValueError(f"{path} does not contain Langfuse public and secret keys")
    return public, secret


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collector-url", default="http://127.0.0.1:4318")
    parser.add_argument("--loki-url", default="http://loki:3100")
    parser.add_argument("--prometheus-url", default="http://prometheus:9090")
    parser.add_argument("--langfuse-url", default="http://langfuse-web:3000")
    parser.add_argument("--query-container", default="aorus-langfuse-langfuse-web")
    parser.add_argument("--credentials", type=Path, default=Path.home() / ".config/aorus-langfuse/credentials.json")
    parser.add_argument("--wait-seconds", type=float, default=30)
    args = parser.parse_args()

    marker = f"telemetry-verify-{secrets.token_hex(12)}"
    trace_id_bytes = secrets.token_bytes(16)
    span_id_bytes = secrets.token_bytes(8)
    trace_id = trace_id_bytes.hex()
    span_id = span_id_bytes.hex()
    now = time.time_ns()
    large_body = marker + ":" + ("unredacted-0123456789abcdef" * 1000)
    attributes = [{"key": "service.name", "value": {"stringValue": "telemetry-verifier"}}]
    resource = {"attributes": attributes}

    log_payload = {
        "resourceLogs": [{"resource": resource, "scopeLogs": [{"scope": {"name": "verify-telemetry"}, "logRecords": [{"timeUnixNano": str(now), "severityNumber": 9, "severityText": "INFO", "body": {"stringValue": large_body}, "attributes": [{"key": "verification.marker", "value": {"stringValue": marker}}]}]}]}]
    }
    trace_payload = {
        "resourceSpans": [{"resource": resource, "scopeSpans": [{"scope": {"name": "verify-telemetry"}, "spans": [{"traceId": trace_id, "spanId": span_id, "name": marker, "kind": 1, "startTimeUnixNano": str(now), "endTimeUnixNano": str(now + 1_000_000), "attributes": [{"key": "verification.marker", "value": {"stringValue": marker}}], "status": {"code": 1}}]}]}]
    }

    def metric_payload(value: int, timestamp: int) -> dict[str, Any]:
        return {
            "resourceMetrics": [{"resource": resource, "scopeMetrics": [{"scope": {"name": "verify-telemetry"}, "metrics": [{"name": "telemetry_verification_delta", "unit": "1", "sum": {"aggregationTemporality": 1, "isMonotonic": True, "dataPoints": [{"startTimeUnixNano": str(now), "timeUnixNano": str(timestamp), "asInt": str(value), "attributes": [{"key": "verification.marker", "value": {"stringValue": marker}}]}]}}]}]}]
        }


    post_otlp(args.collector_url, "logs", log_payload)
    post_otlp(args.collector_url, "metrics", metric_payload(2, now + 2_000_000))
    post_otlp(args.collector_url, "metrics", metric_payload(3, now + 3_000_000))
    post_otlp(args.collector_url, "traces", trace_payload)

    deadline = time.monotonic() + args.wait_seconds
    log_verified = metric_verified = trace_verified = disk_metric_verified = False
    observed_metric: float | None = None

    public, secret = credentials(args.credentials)
    basic = base64.b64encode(f"{public}:{secret}".encode()).decode()
    auth_headers = {"Authorization": f"Basic {basic}"}

    while time.monotonic() < deadline and not (log_verified and metric_verified and trace_verified and disk_metric_verified):
        if not log_verified:
            query = urllib.parse.urlencode({"query": f'{{service_name="telemetry-verifier"}} |= `{marker}`', "limit": "10"})
            result = container_request_json(args.query_container, f"{args.loki_url}/loki/api/v1/query_range?{query}")
            values = [entry[1] for stream in result.get("data", {}).get("result", []) for entry in stream.get("values", [])]
            log_verified = any(value == large_body for value in values)
        if not metric_verified:
            query = urllib.parse.urlencode({"query": f'telemetry_verification_delta_total{{verification_marker="{marker}"}}'})
            result = container_request_json(args.query_container, f"{args.prometheus_url}/api/v1/query?{query}")
            samples = result.get("data", {}).get("result", [])
            if samples:
                observed_metric = float(samples[0]["value"][1])
                metric_verified = math.isclose(observed_metric, 5.0)
        if not disk_metric_verified:
            query = urllib.parse.urlencode({"query": 'system_filesystem_usage_bytes{mountpoint="/host-data",state="used"}'})
            result = container_request_json(args.query_container, f"{args.prometheus_url}/api/v1/query?{query}")
            disk_metric_verified = bool(result.get("data", {}).get("result", []))
        if not trace_verified:
            try:
                query = urllib.parse.urlencode({"traceId": trace_id, "limit": "10"})
                result = container_request_json(args.query_container, f"{args.langfuse_url}/api/public/v2/observations?{query}", auth_headers)
                trace_verified = any(item.get("traceId") == trace_id for item in result.get("data", []))
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
        if not (log_verified and metric_verified and trace_verified and disk_metric_verified):
            time.sleep(2)

    summary = {
        "marker": marker,
        "large_log_bytes": len(large_body.encode()),
        "large_log_exact_match": log_verified,
        "delta_expected": 5,
        "delta_observed": observed_metric,
        "delta_accumulated": metric_verified,
        "host_data_filesystem_metric": disk_metric_verified,
        "trace_id": trace_id,
        "trace_found": trace_verified,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if log_verified and metric_verified and trace_verified and disk_metric_verified else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, urllib.error.URLError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
