# Privacy, Robustness, and Ethics

## Privacy and Security

Documents may contain personally identifiable information:

- Names
- Addresses
- Phone numbers
- Emails
- Tax codes
- Bank or payment information
- Signatures

Privacy controls:

- Do not commit raw private documents.
- Keep `api_key.env`, `.env`, model checkpoints, and private data ignored by Git.
- Use anonymized or synthetic samples in the public repository.
- Minimize LLM usage for sensitive documents.
- If LLM is enabled, send only the OCR text needed for correction and QA.

## Robustness

Robustness risks:

- Blurry images.
- Tilted or perspective-distorted scans.
- Low contrast paper.
- Handwritten text.
- Unseen layouts.
- Out-of-domain documents that mention invoice-like words.

Mitigation:

- Optional preprocessing with skew handling.
- Conservative invoice classification.
- LayoutXLM only for invoice/receipt cases.
- Warnings for low-confidence words and missing required fields.
- User-visible AI status and extracted-field confidence.
- Fallback to raw OCR text when advanced models are unavailable.

## Ethical Impact

Who benefits:

- Accounting and operations teams gain time savings.
- Users can search and export scanned documents faster.
- Organizations reduce repetitive manual entry.

Who could be harmed:

- People whose private documents are processed without consent.
- Employees if automation is introduced without workflow planning.
- Users who rely on incorrect extracted totals or identities.

## Bias and Fairness

Potential bias:

- Better performance on clean English invoices than Vietnamese or low-quality scans.
- Public datasets may not represent local business formats.
- Rare templates may receive lower extraction accuracy.

Mitigation:

- Evaluate separately by language and document type.
- Include Vietnamese invoices and mobile-photo examples in the test set.
- Surface uncertainty and do not hide low-confidence warnings.

## Explainability

The system provides:

- Bounding boxes on the document.
- Extracted fields with source labels.
- Warnings for missing or low-confidence values.
- AI agent trace for LLM/LayoutXLM-assisted extraction.
- Monitoring dashboard for operational behavior.

## Misuse

Potential misuse:

- Bulk extraction of private document information.
- Automated decisions based on unverified OCR output.
- Uploading confidential documents to a third-party LLM.

Mitigation:

- Keep LLM optional and disabled by default.
- Add access control before production use.
- Log usage and monitor abnormal API patterns.
- Require human review for high-risk financial decisions.
