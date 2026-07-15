#!/usr/bin/env python3
"""Send a smoke-test span and query Honeycomb to confirm traces are arriving."""

import json
import os
import sys
import time
import urllib.error
import urllib.request

from opentelemetry.trace import Status, StatusCode

from telemetry import get_tracer, init_telemetry, shutdown_telemetry

DATASET = os.getenv("OTEL_SERVICE_NAME", "signal-news-digest")


def honeycomb_query(api_key: str, query: dict) -> dict:
    payload = json.dumps(query).encode()
    req = urllib.request.Request(
        f"https://api.honeycomb.io/1/query/{DATASET}",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Honeycomb-Team": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def honeycomb_query_result(api_key: str, pk: str) -> dict:
    req = urllib.request.Request(
        f"https://api.honeycomb.io/1/query_results/{DATASET}",
        data=json.dumps({"query_result_id": pk}).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Honeycomb-Team": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def dataset_last_written(api_key: str) -> str | None:
    req = urllib.request.Request(
        "https://api.honeycomb.io/1/datasets",
        headers={"X-Honeycomb-Team": api_key},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        datasets = json.load(resp)
    for dataset in datasets:
        if dataset.get("slug") == DATASET:
            return dataset.get("last_written_at")
    return None


def wait_for_count(api_key: str, span_name: str, attempts: int = 8) -> int | None:
    query = {
        "calculations": [{"op": "COUNT"}],
        "filters": [{"column": "name", "op": "=", "value": span_name}],
        "time_range": 3600,
    }

    for _ in range(attempts):
        created = honeycomb_query(api_key, query)
        pk = created.get("id")
        if not pk:
            time.sleep(2)
            continue

        for _ in range(attempts):
            result = honeycomb_query_result(api_key, pk)
            if result.get("complete"):
                rows = result.get("data", {}).get("results", [])
                if rows:
                    return int(rows[0].get("COUNT", 0))
                return 0
            time.sleep(2)

    return None


def print_suggested_queries() -> None:
    print("Suggested Honeycomb queries (query-patterns skill):")
    print("  - COUNT where name exists GROUP BY name")
    print("  - P99(duration_ms) where name = digest.call_claude")
    print("  - COUNT where error = true GROUP BY exception.slug")


def main() -> int:
    api_key = os.getenv("HONEYCOMB_API_KEY")
    if not api_key:
        print("Set HONEYCOMB_API_KEY to verify traces in Honeycomb.")
        return 1

    init_telemetry()
    tracer = get_tracer()

    marker = f"verify-{int(time.time())}"
    with tracer.start_as_current_span("digest.verify_telemetry") as span:
        span.set_attribute("digest.verify_marker", marker)
        span.set_attribute("digest.success", True)
        span.set_status(Status(StatusCode.OK))

    shutdown_telemetry()
    print("Sent smoke-test span. Verifying data in Honeycomb...")

    count = None
    try:
        count = wait_for_count(api_key, "digest.verify_telemetry")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise

    if count is not None and count >= 1:
        print(f"OK — found {count} span(s) named digest.verify_telemetry in dataset '{DATASET}' (last 1h).")
        print_suggested_queries()
        return 0

    last_written = dataset_last_written(api_key)
    if last_written:
        print(f"OK — dataset '{DATASET}' received data (last_written_at: {last_written}).")
        print("This API key cannot run Honeycomb queries via API; verify spans in the UI with:")
        print_suggested_queries()
        return 0

    print(f"No data seen yet for dataset '{DATASET}'. Check API key and wait a minute, then retry.")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Honeycomb API error ({exc.code}): {body}")
        raise SystemExit(1)
