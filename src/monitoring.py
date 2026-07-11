from __future__ import annotations

import os
import platform
import statistics
import threading
import time
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round_rate(value: float) -> float:
    return round(max(0.0, min(value, 1.0)), 4)


class SystemMonitor:
    """Small in-memory monitor for API and OCR quality signals.

    This is intentionally dependency-free. It gives the UI enough live data for
    local development and Docker deployments; production deployments can later
    forward these events to Prometheus, Grafana, or a database.
    """

    def __init__(self, max_request_samples: int = 500, max_ocr_samples: int = 200):
        self.started_at = time.time()
        self._requests: deque[dict[str, Any]] = deque(maxlen=max_request_samples)
        self._ocr_runs: deque[dict[str, Any]] = deque(maxlen=max_ocr_samples)
        self._lock = threading.Lock()

    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        latency_ms: float,
    ) -> None:
        with self._lock:
            self._requests.append(
                {
                    "timestamp": _now_iso(),
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "latency_ms": round(latency_ms, 2),
                    "is_error": status_code >= 400,
                }
            )

    def record_ocr_run(
        self,
        filename: str,
        document_type: str,
        duration_ms: float,
        quality: dict[str, Any],
        ai_analysis: dict[str, Any],
    ) -> None:
        llm_status = _nested_status(ai_analysis.get("llm"))
        layoutxlm_status = _nested_status(ai_analysis.get("layoutxlm"))
        with self._lock:
            self._ocr_runs.append(
                {
                    "timestamp": _now_iso(),
                    "filename": filename,
                    "document_type": document_type,
                    "duration_ms": round(duration_ms, 2),
                    "estimated_raw_error_rate": quality["estimated_raw_error_rate"],
                    "estimated_after_ai_error_rate": quality["estimated_after_ai_error_rate"],
                    "estimated_improvement_rate": quality["estimated_improvement_rate"],
                    "word_count": quality["word_count"],
                    "low_confidence_word_count": quality["low_confidence_word_count"],
                    "missing_required_fields": quality["missing_required_fields"],
                    "warning_count": quality["warning_count"],
                    "quality_level": quality["quality_level"],
                    "llm_status": llm_status,
                    "layoutxlm_status": layoutxlm_status,
                }
            )

    def health(self, services: dict[str, Any] | None = None) -> dict[str, Any]:
        snapshot = self.snapshot(services=services, recent_limit=5)
        request_error_rate = snapshot["api"]["error_rate"]
        latest_quality = snapshot["ocr"]["latest"]
        status = "ok"
        if request_error_rate >= 0.2:
            status = "degraded"
        if latest_quality and latest_quality.get("quality_level") == "poor":
            status = "degraded"

        return {
            "status": status,
            "timestamp": _now_iso(),
            "uptime_seconds": snapshot["uptime_seconds"],
            "api": snapshot["api"],
            "ocr": snapshot["ocr"],
            "services": services or {},
        }

    def snapshot(
        self,
        services: dict[str, Any] | None = None,
        recent_limit: int = 20,
    ) -> dict[str, Any]:
        with self._lock:
            requests = list(self._requests)
            ocr_runs = list(self._ocr_runs)

        return {
            "timestamp": _now_iso(),
            "uptime_seconds": round(time.time() - self.started_at, 2),
            "host": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "pid": os.getpid(),
            },
            "api": self._api_summary(requests, recent_limit),
            "ocr": self._ocr_summary(ocr_runs, recent_limit),
            "services": services or {},
        }

    def _api_summary(
        self,
        requests: list[dict[str, Any]],
        recent_limit: int,
    ) -> dict[str, Any]:
        total = len(requests)
        errors = sum(1 for item in requests if item["is_error"])
        latencies = [float(item["latency_ms"]) for item in requests]
        path_counts = Counter(item["path"] for item in requests)
        status_counts = Counter(str(item["status_code"]) for item in requests)

        return {
            "requests_total": total,
            "errors_total": errors,
            "error_rate": _round_rate(errors / total) if total else 0.0,
            "latency_ms": {
                "avg": _safe_mean(latencies),
                "p50": _percentile(latencies, 50),
                "p95": _percentile(latencies, 95),
                "max": round(max(latencies), 2) if latencies else 0.0,
            },
            "by_path": dict(path_counts.most_common(10)),
            "by_status": dict(status_counts),
            "recent": requests[-recent_limit:][::-1],
        }

    def _ocr_summary(
        self,
        ocr_runs: list[dict[str, Any]],
        recent_limit: int,
    ) -> dict[str, Any]:
        total = len(ocr_runs)
        raw_rates = [float(item["estimated_raw_error_rate"]) for item in ocr_runs]
        after_rates = [float(item["estimated_after_ai_error_rate"]) for item in ocr_runs]
        durations = [float(item["duration_ms"]) for item in ocr_runs]
        poor_runs = sum(1 for item in ocr_runs if item.get("quality_level") == "poor")

        return {
            "runs_total": total,
            "poor_runs_total": poor_runs,
            "poor_rate": _round_rate(poor_runs / total) if total else 0.0,
            "average_raw_error_rate": _safe_mean(raw_rates),
            "average_after_ai_error_rate": _safe_mean(after_rates),
            "average_improvement_rate": _round_rate(
                max(_safe_mean(raw_rates) - _safe_mean(after_rates), 0.0)
            ),
            "duration_ms": {
                "avg": _safe_mean(durations),
                "p95": _percentile(durations, 95),
                "max": round(max(durations), 2) if durations else 0.0,
            },
            "latest": ocr_runs[-1] if ocr_runs else None,
            "recent": ocr_runs[-recent_limit:][::-1],
        }


def estimate_ocr_quality(
    structured_data: dict[str, Any],
    extracted_text: str,
    ai_analysis: dict[str, Any],
) -> dict[str, Any]:
    words = _extract_words(structured_data)
    word_count = len(words)
    low_confidence_words = [
        word for word in words if word["confidence"] is not None and word["confidence"] < 0.55
    ]

    if not extracted_text.strip():
        raw_error_rate = 1.0
    elif word_count:
        raw_error_rate = len(low_confidence_words) / word_count
    else:
        raw_error_rate = 0.0

    warnings = ai_analysis.get("warnings") or []
    document_type = ai_analysis.get("document_type") or "general_document"
    fields = ai_analysis.get("fields") or {}
    missing_required_fields = _missing_required_fields(document_type, fields)
    field_issue_rate = _field_issue_rate(document_type, missing_required_fields, warnings)

    ai_factor = 1.0
    llm = ai_analysis.get("llm") or {}
    layoutxlm = ai_analysis.get("layoutxlm") or {}
    corrected_text = llm.get("full_corrected_text") or ai_analysis.get("full_corrected_text")
    if llm.get("status") == "ok":
        ai_factor = min(ai_factor, 0.55 if corrected_text else 0.75)
    if layoutxlm.get("status") == "ok":
        ai_factor = min(ai_factor, 0.85)

    after_ai_error_rate = max(raw_error_rate * ai_factor, field_issue_rate)
    raw_error_rate = _round_rate(raw_error_rate)
    after_ai_error_rate = _round_rate(after_ai_error_rate)
    improvement_rate = _round_rate(max(raw_error_rate - after_ai_error_rate, 0.0))

    return {
        "estimated_raw_error_rate": raw_error_rate,
        "estimated_after_ai_error_rate": after_ai_error_rate,
        "estimated_improvement_rate": improvement_rate,
        "word_count": word_count,
        "low_confidence_word_count": len(low_confidence_words),
        "missing_required_fields": missing_required_fields,
        "warning_count": len(warnings),
        "quality_level": _quality_level(after_ai_error_rate),
        "note": (
            "Estimated from OCR word confidence, missing required fields, "
            "AI correction status, and remaining warnings. It is not a ground-truth error rate."
        ),
    }


def _extract_words(structured_data: dict[str, Any]) -> list[dict[str, Any]]:
    words = []
    for page in structured_data.get("pages", []):
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                for word in line.get("words", []):
                    value = str(word.get("value") or "").strip()
                    if not value:
                        continue
                    confidence = word.get("confidence")
                    words.append(
                        {
                            "value": value,
                            "confidence": float(confidence) if confidence is not None else None,
                        }
                    )
    return words


def _missing_required_fields(document_type: str, fields: dict[str, Any]) -> list[str]:
    required_by_type = {
        "invoice": ["invoice_number", "total_amount"],
        "receipt": ["total_amount"],
        "contract": ["primary_date"],
    }
    required = required_by_type.get(document_type, [])
    return [field for field in required if field not in fields]


def _field_issue_rate(
    document_type: str,
    missing_required_fields: list[str],
    warnings: list[dict[str, Any]],
) -> float:
    if document_type not in {"invoice", "receipt", "contract"}:
        return 0.0

    severity_weight = {"low": 0.25, "medium": 0.5, "high": 1.0}
    warning_score = sum(
        severity_weight.get(str(item.get("severity", "medium")), 0.5)
        for item in warnings
    )
    required_score = len(missing_required_fields)
    denominator = max(3.0, len(missing_required_fields) + 3.0)
    return _round_rate(min((warning_score + required_score) / denominator, 1.0))


def _quality_level(after_ai_error_rate: float) -> str:
    if after_ai_error_rate >= 0.35:
        return "poor"
    if after_ai_error_rate >= 0.15:
        return "degraded"
    return "good"


def _nested_status(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("status") or "unknown")
    return "unknown"


def _safe_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(statistics.fmean(values), 2 if max(values, default=0.0) > 1 else 4)


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((percentile / 100) * (len(ordered) - 1)))
    return round(ordered[index], 2)
