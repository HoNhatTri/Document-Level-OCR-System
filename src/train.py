from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.agent import DocumentAgent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Tune lightweight document-agent thresholds on OCR text manifests. "
            "Fine-tuned LayoutXLM training uses word-level BIO labels and "
            "normalized 0-1000 boxes. Place the exported checkpoint in models/."
        )
    )
    parser.add_argument("--train-manifest", required=True, help="JSONL manifest with text and labels.")
    parser.add_argument("--validation-manifest", required=True, help="JSONL manifest with text and labels.")
    parser.add_argument("--output", default="configs/tuned_agent_config.json", help="Output config path.")
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
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


def score_threshold(rows: list[dict[str, Any]], invoice_threshold: int) -> float:
    agent = DocumentAgent()
    correct = 0
    labeled = 0
    for item in rows:
        expected = item.get("document_type")
        text = item.get("text", "")
        if not expected or not text:
            continue
        predicted = classify_with_threshold(agent, text, invoice_threshold)
        correct += int(predicted == expected)
        labeled += 1
    return correct / labeled if labeled else 0.0


def classify_with_threshold(agent: DocumentAgent, text: str, invoice_threshold: int) -> str:
    normalized = agent._normalize(text)
    invoice_score = agent._score_invoice(normalized)
    if invoice_score >= invoice_threshold:
        return "invoice"

    scores: dict[str, int] = {}
    for document_type, keywords in agent.DOCUMENT_KEYWORDS.items():
        if document_type == "invoice":
            continue
        score = sum(agent._contains_phrase(normalized, keyword) for keyword in keywords)
        if score:
            scores[document_type] = score
    if not scores:
        return "general_document"
    return max(scores.items(), key=lambda item: item[1])[0]


def main() -> None:
    args = parse_args()
    train_rows = load_jsonl(Path(args.train_manifest))
    validation_rows = load_jsonl(Path(args.validation_manifest))
    candidates = range(2, 8)

    train_scores = {
        threshold: score_threshold(train_rows, threshold)
        for threshold in candidates
    }
    validation_scores = {
        threshold: score_threshold(validation_rows, threshold)
        for threshold in candidates
    }
    best_threshold = max(validation_scores, key=validation_scores.get)

    output = {
        "document_agent": {
            "invoice_keyword_threshold": best_threshold,
            "note": (
                "This config records lightweight threshold tuning for the rule-based "
                "agent. Update src.agent.DocumentAgent._classify if you choose to "
                "promote this tuned value into production."
            ),
        },
        "train_scores": train_scores,
        "validation_scores": validation_scores,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
