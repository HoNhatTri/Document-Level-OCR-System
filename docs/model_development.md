# Model Development and Evaluation

## Model Selection

The system combines multiple model layers:

- OCR detector/recognizer from `python-doctr`.
- Rule-based document agent for deterministic document type and field extraction.
- Generic key-value extractor for unseen labels.
- Optional LayoutXLM/LayoutLMv2 token classifier fine-tuned for invoice/receipt entities.
- Optional Groq-hosted LLM for OCR correction, summarization, and document QA.

This hybrid design is chosen because document OCR requires both visual recognition and semantic understanding. Rules are fast and maintainable for common fields, LayoutXLM improves layout-aware extraction, and the LLM handles OCR correction and flexible question answering.

## Baselines

Baseline 1:

- Raw OCR text only.
- No field extraction, no table detection, no AI correction.

Baseline 2:

- OCR plus deterministic rules.
- No LayoutXLM and no LLM.

Full system:

- OCR, preprocessing, table extraction, rule agent, generic key-value extraction, optional LayoutXLM, optional LLM, and monitoring.

## Hyperparameter Tuning

Lightweight tuning is supported by:

```bash
python -m src.train \
  --train-manifest data/manifests/train.jsonl \
  --validation-manifest data/manifests/validation.jsonl \
  --output configs/tuned_agent_config.json
```

The script searches invoice keyword thresholds for the rule-based document classifier.

For LayoutXLM fine-tuning, prepare word-level BIO labels with normalized 0-1000 boxes and fine-tune a `LayoutLMv2ForTokenClassification`/LayoutXLM-compatible model. Store the exported checkpoint outside Git and mount it at:

```text
model/layoutxlm-sroie-mcocr
```

## Evaluation

Run evaluation with:

```bash
python -m src.evaluate \
  --manifest data/manifests/test.jsonl \
  --output data/manifests/evaluation_results.json
```

The evaluator reports:

- Document type accuracy.
- Field-level exact-match accuracy.
- Average latency.
- p95 latency.
- Per-document errors and warnings.

## Error Analysis

Known failure cases:

- Blurred images where characters cannot be recovered.
- Heavy rotation or perspective distortion.
- Dense Vietnamese tax invoice layouts with similar labels.
- Tables without clear line structure.
- Out-of-domain documents that mention invoice keywords but are not invoices.

Mitigation:

- Keep preprocessing configurable.
- Add evaluation samples for each failure category.
- Use LayoutXLM only for invoice/receipt-like documents.
- Keep AI extracted values conservative and do not invent missing fields.

## Trade-offs

Accuracy vs speed:

- Rule extraction is fast and deterministic.
- LayoutXLM improves layout-aware extraction but adds model load and inference cost.
- LLM improves correction and QA but adds network latency and privacy considerations.

Complexity vs maintainability:

- The base OCR path works offline.
- Optional components are lazy-loaded and can fail gracefully.
- Monitoring exposes latency and quality signals for operational tuning.
