from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import error
from urllib import request


BASE_DIR = Path(__file__).resolve().parent
TEST_CASES_PATH = BASE_DIR / "test-cases.json"
ENDPOINT = os.environ.get("RELAY_ENDPOINT", "http://127.0.0.1:8020/api/diagnose").strip()


def main() -> int:
    test_cases = json.loads(TEST_CASES_PATH.read_text(encoding="utf-8"))
    passed = 0
    category_hits = 0
    service_hits = 0
    request_errors = 0

    for index, case in enumerate(test_cases, start=1):
        payload = json.dumps({"text": case["query"]}, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            request_errors += 1
            print(
                json.dumps(
                    {
                        "case": index,
                        "query": case["query"],
                        "ok": False,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )
            )
            continue

        matched_categories = {item["category"] for item in result.get("matches", [])}
        matched_services = {item["name"] for item in result.get("matches", [])}
        expected_categories = set(case["expected_categories"])
        expected_services = set(case["expected_services"])
        category_ok = bool(matched_categories & expected_categories)
        service_ok = bool(matched_services & expected_services)
        ok = category_ok and service_ok
        passed += int(ok)
        category_hits += int(category_ok)
        service_hits += int(service_ok)

        print(
            json.dumps(
                {
                    "case": index,
                    "query": case["query"],
                    "ok": ok,
                    "category_ok": category_ok,
                    "service_ok": service_ok,
                    "expected_categories": sorted(expected_categories),
                    "expected_services": sorted(expected_services),
                    "matched_categories": sorted(matched_categories),
                    "matched_services": sorted(matched_services),
                    "reason": result.get("reason", ""),
                },
                ensure_ascii=False,
            )
        )

    print(
        json.dumps(
            {
                "passed": passed,
                "total": len(test_cases),
                "category_hits": category_hits,
                "service_hits": service_hits,
                "request_errors": request_errors,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
