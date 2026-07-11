# Models

This directory documents trained model artifacts for submission compatibility.

Large checkpoints are not committed to GitHub. The project uses:

- `python-doctr` OCR detector: `db_resnet50`
- `python-doctr` OCR recognizer: `crnn_vgg16_bn`
- Optional fine-tuned LayoutXLM/LayoutLMv2 token classifier for invoices and receipts
- Optional Groq-hosted LLM for OCR correction, summarization, and document QA

Model artifacts should be stored outside Git and referenced through:

- `LAYOUTXLM_MODEL_PATH`
- Docker volume `./model:/app/model:ro`
- `model/README.md`

For training and evaluation commands, see the root `README.md` and `docs/model_development.md`.
