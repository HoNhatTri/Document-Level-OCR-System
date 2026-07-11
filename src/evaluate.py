from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from src.agent import DocumentAgent
from src.ocr_engine import OCREngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate OCR + document agent on a JSONL manifest.")
    parser.add_argument("--manifest", required=True, help="Path to JSONL evaluation manifest.")
    parser.add_argument("--config", default="configs/model_config.yaml", help="OCR model config path.")
    parser.add_argument("--max-documents", type=int, default=0, help="Optional limit for smoke runs.")
    parser.add_argument("--output", default="", help="Optional JSON file for metrics.")
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
    return rows


def normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value).replace(",", "").strip().lower()
    return " ".join(str(value).replace(",", "").strip().lower().split())


def field_value(field: Any) -> Any:
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def evaluate_document(
    engine: OCREngine,
    agent: DocumentAgent,
    item: dict[str, Any],
) -> dict[str, Any]:
    file_path = item.get("file_path") or item.get("image_path") or item.get("path")
    if not file_path:
        raise ValueError("Manifest item is missing file_path/image_path/path.")

    started = time.perf_counter()
    raw_result = engine.process_document(str(file_path))
    structured_data = engine.get_structured_data(raw_result)
    structured_data["_processing"] = engine.get_processing_info()
    extracted_text = engine.get_raw_text(raw_result, structured_data=structured_data)
    bounding_boxes = engine.get_bounding_boxes(structured_data)
    page_images = engine.take_document_images()
    analysis = agent.analyze(
        extracted_text=extracted_text,
        structured_data=structured_data,
        bounding_boxes=bounding_boxes,
        page_images=page_images,
    )
    latency_ms = (time.perf_counter() - started) * 1000

    expected_type = item.get("document_type")
    predicted_type = analysis.get("document_type")
    expected_fields = item.get("fields") or {}
    predicted_fields = analysis.get("fields") or {}
    correct_fields = 0
    checked_fields = 0
    field_details = {}

    for name, expected_value in expected_fields.items():
        checked_fields += 1
        predicted_value = field_value(predicted_fields.get(name))
        is_correct = normalize_value(predicted_value) == normalize_value(expected_value)
        correct_fields += int(is_correct)
        field_details[name] = {
            "expected": expected_value,
            "predicted": predicted_value,
            "correct": is_correct,
        }

    return {
        "file_path": str(file_path),
        "latency_ms": round(latency_ms, 2),
        "expected_document_type": expected_type,
        "predicted_document_type": predicted_type,
        "document_type_correct": expected_type == predicted_type if expected_type else None,
        "checked_fields": checked_fields,
        "correct_fields": correct_fields,
        "field_accuracy": round(correct_fields / checked_fields, 4) if checked_fields else None,
        "field_details": field_details,
        "warnings": analysis.get("warnings", []),
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "documents": 0,
            "document_type_accuracy": None,
            "field_accuracy": None,
            "average_latency_ms": None,
        }

    typed = [item for item in results if item["document_type_correct"] is not None]
    total_fields = sum(item["checked_fields"] for item in results)
    correct_fields = sum(item["correct_fields"] for item in results)
    average_latency = sum(item["latency_ms"] for item in results) / len(results)

    return {
        "documents": len(results),
        "document_type_accuracy": round(
            sum(item["document_type_correct"] for item in typed) / len(typed),
            4,
        )
        if typed
        else None,
        "field_accuracy": round(correct_fields / total_fields, 4) if total_fields else None,
        "checked_fields": total_fields,
        "correct_fields": correct_fields,
        "average_latency_ms": round(average_latency, 2),
        "p95_latency_ms": percentile([item["latency_ms"] for item in results], 95),
    }


def percentile(values: list[float], percentile_value: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((percentile_value / 100) * (len(ordered) - 1))
    return round(ordered[index], 2)


def main() -> None:
    args = parse_args()
    manifest = load_manifest(Path(args.manifest))
    if args.max_documents > 0:
        manifest = manifest[: args.max_documents]

    engine = OCREngine(config_path=args.config)
    agent = DocumentAgent()
    results = [evaluate_document(engine, agent, item) for item in manifest]
    payload = {
        "summary": summarize(results),
        "results": results,
    }

    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
