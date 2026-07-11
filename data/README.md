# Data Management

This project is designed for public, synthetic, or anonymized document data.

## Expected Data Sources

- Public OCR/document datasets:
  - SROIE for receipt information extraction
  - MC-OCR or equivalent Vietnamese receipt/invoice OCR datasets
  - User-provided synthetic invoice templates for functional testing
- Local private data:
  - Allowed only after removing or masking personally identifiable information
  - Must not be committed to Git

## Directory Layout

```text
data/
├── raw/                  # Original local/private files, ignored by Git
├── processed/            # Cleaned OCR-ready files, ignored by Git
├── manifests/            # JSONL train/validation/test manifests
├── sample_images/        # Small non-sensitive samples for smoke tests
└── exported_document.*   # Generated exports, ignored by Git
```

## Manifest Format

Training/evaluation scripts expect JSONL manifests. One line represents one document.

```json
{
  "file_path": "data/processed/invoice_001.png",
  "document_type": "invoice",
  "fields": {
    "invoice_number": "INV-001",
    "total_amount": "2338.35",
    "buyer": "Ms. Mary D. Dunton"
  }
}
```

LayoutXLM fine-tuning can additionally use word-level labels:

```json
{
  "image_path": "data/processed/invoice_001.png",
  "words": ["Invoice", "#", "INV-001"],
  "boxes": [[100, 100, 180, 130], [185, 100, 200, 130], [210, 100, 310, 130]],
  "labels": ["O", "O", "B-INVOICE_NUMBER"]
}
```

Boxes are normalized to the 0-1000 LayoutLM/LayoutXLM coordinate space.

## Preprocessing

The OCR pipeline supports:

- Resize for low-resolution images
- Contrast enhancement
- Light denoising
- Thresholding for scanned documents
- Skew detection and page rectification for tilted scans

Preprocessing can be toggled in the web settings panel.

## Data Split Policy

Recommended split:

- Train: 70%
- Validation: 15%
- Test: 15%

Splits should be stratified by document type and language whenever possible.

## Known Limitations and Biases

- Public invoice/receipt datasets may over-represent clean scans and under-represent mobile photos.
- English invoice templates are easier than Vietnamese tax invoices with dense fields.
- OCR confidence is not a perfect proxy for correctness.
- Handwritten, blurred, or heavily rotated documents remain high-risk cases.

## Privacy

Do not commit raw documents that contain names, addresses, phone numbers, tax codes, emails, or signatures.
Use synthetic or anonymized samples for the public repository.
