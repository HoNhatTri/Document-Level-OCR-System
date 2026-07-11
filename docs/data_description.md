# Data Description

## Data Sources

The project supports three data categories:

- Public datasets such as SROIE and MC-OCR for receipt/invoice extraction.
- Synthetic invoice/form images for smoke tests and UI demonstrations.
- Private business documents after anonymization.

Private documents must not be committed to the public repository.

## Licensing

Public datasets must be used according to their original licenses. Synthetic samples can be shared if they do not reproduce private customer data. Any internal company data must be treated as confidential and excluded from Git.

## Dataset Size and Languages

The expected production dataset contains:

- English invoices and generic documents.
- Vietnamese invoices, receipts, and forms.
- PDFs and image formats: PNG, JPG, JPEG, PDF.

The repository contains only small sample files. Full datasets and model checkpoints are stored externally.

## Data Format

Evaluation manifests use JSONL:

```json
{"file_path":"data/processed/invoice_001.png","document_type":"invoice","fields":{"invoice_number":"INV-001","total_amount":"2338.35"}}
```

LayoutXLM fine-tuning manifests can include `words`, `boxes`, and BIO labels.

## Preprocessing Steps

Implemented preprocessing includes:

- Resize and contrast enhancement.
- Denoising.
- Thresholding for scan-like images.
- Skew detection and rectification for tilted pages.
- Optional disabling through the settings UI.

## Train/Validation/Test Split

Recommended split:

- Train: 70%
- Validation: 15%
- Test: 15%

The split should be stratified by language, document type, and image source. Documents from the same invoice template or vendor should not be split across train and test if the goal is template generalization.

## Missing, Noisy, and Biased Data

Handling strategy:

- Missing labels are skipped during field-level evaluation.
- Low-confidence OCR words are surfaced as warnings.
- Skewed and low-contrast images go through preprocessing.
- Vietnamese invoices require separate test coverage because English invoice templates are easier.

Known limitations:

- Blurred images may remain unreadable even after preprocessing.
- OCR confidence is not always equal to correctness.
- Public datasets may not represent real mobile-photo conditions.
