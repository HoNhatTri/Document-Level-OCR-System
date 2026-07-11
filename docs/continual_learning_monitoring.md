# Continual Learning and Monitoring

## Continual Learning Strategy

New data collection:

- Capture user corrections for extracted fields.
- Log missing-field warnings and low-confidence OCR words.
- Allow users to flag wrong document type or wrong table extraction.
- Store only anonymized examples for training.

Retraining:

- Review new labeled examples monthly or after a fixed number of corrections.
- Add hard examples: blurred scans, Vietnamese invoices, skewed images, and unusual layouts.
- Re-run evaluation on a frozen test set before promotion.
- Promote a new LayoutXLM checkpoint only if it improves field accuracy without unacceptable latency.

Fine-tuning:

- Fine-tune LayoutXLM/LayoutLMv2 for token classification using word boxes and BIO labels.
- Keep deterministic rules as a fallback for fields not covered by the model.
- Use validation metrics to tune confidence thresholds.

## Monitoring Metrics

Implemented metrics:

- API request count.
- API error rate.
- Average, p50, p95, and max latency.
- OCR run count.
- Estimated OCR error rate before AI correction.
- Estimated OCR error rate after AI correction.
- Estimated improvement from AI.
- Latest LLM and LayoutXLM status.

Available endpoints:

- `GET /api/health`
- `GET /api/monitoring`
- `GET /api/metrics`

## Drift Risks

Data drift:

- New invoice templates.
- New languages.
- More mobile photos instead of clean scans.
- New tax or accounting formats.

Model drift:

- Existing field rules stop matching new layouts.
- LayoutXLM confidence drops on unseen vendors.
- LLM output quality changes across hosted model versions.

## Mitigation

- Track field accuracy on a fixed test set.
- Track monitoring metrics over time.
- Keep sample sets by language and document type.
- Review low-confidence and missing-field examples.
- Version all model artifacts and configs.
- Roll back to the previous model if latency or extraction quality degrades.
