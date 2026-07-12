# Document-Level OCR System

End-to-end OCR and document intelligence system for invoices, receipts, contracts, forms, and general scanned documents. The system converts document images/PDFs into text, tables, structured JSON, extracted business fields, exportable PDF/DOCX files, and AI-assisted question answering.

## Project Overview

Business problem:

- Manual document entry is slow and error-prone.
- Invoices and scanned documents often contain noisy OCR text, tables, skewed images, and mixed Vietnamese/English content.
- Users need a practical system that reads documents, extracts important information, and exposes results through a web interface and REST API.

Core capabilities:

- OCR for PDF, PNG, JPG, and JPEG.
- Optional image preprocessing and skew correction.
- Document type classification.
- Invoice/receipt field extraction.
- Generic key-value extraction for unseen templates.
- Table and layout region detection.
- Optional LayoutXLM/LayoutLMv2 model for invoice/receipt entities.
- Optional LLM correction, Vietnamese diacritics support, summarization, and document QA.
- Export OCR result to PDF and Word.
- Docker deployment.
- API and OCR quality monitoring.

## Repository Structure

```text
project-root/
|-- src/                         # Backend, OCR, AI agent, monitoring, train/evaluate scripts
|-- data/                        # Data scripts, sample images, manifest examples
|-- models/                      # Local large model artifacts, ignored by Git
|-- configs/                     # OCR and tuned config files
|-- tests/                       # Unit tests
|-- UI/Data Export Interface/    # React/Vite frontend
|-- Dockerfile.backend
|-- docker-compose.yml
|-- requirements.txt
`-- README.md
```

## Environment Setup

Python 3.11 is recommended.

```bash
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Frontend:

```bash
cd "UI\Data Export Interface"
npm install
```

The frontend source is in `UI/Data Export Interface`. It is the React/Vite
implementation of the Data Export Interface design and is started with
`npm run dev`.

## Run the System Locally

Terminal 1, backend:

```bash
python -m uvicorn src.app:app --reload
```

Terminal 2, frontend:

```bash
cd "UI\Data Export Interface"
npm run dev
```

Open:

```text
http://localhost:5173
```

The Vite dev server proxies `/api` requests to `http://localhost:8000`.

## Run with Docker

```bash
docker compose up --build
```

URLs:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Health: `http://localhost:8000/api/health`
- Monitoring: `http://localhost:8000/api/monitoring`

Large model files are not copied into Docker images. Put local checkpoints under `models/` and Docker Compose will mount them into the backend container.

## API Inference

Upload a document:

```bash
curl -X POST "http://localhost:8000/api/upload" \
  -F "file=@data/sample_images/test.jpg"
```

Main API endpoints:

- `POST /api/upload`
- `POST /api/analyze`
- `POST /api/chat`
- `POST /api/layout`
- `POST /api/export-pdf`
- `POST /api/export-docx`
- `GET /api/settings`
- `PUT /api/settings`
- `GET /api/health`
- `GET /api/monitoring`
- `GET /api/layoutxlm/status`

Output contains:

- `extracted_text`
- `json_data`
- `tables`
- `layout_regions`
- `ai_analysis`
- `bounding_boxes`

## Train or Tune Models

Lightweight document-agent threshold tuning:

```bash
python -m src.train \
  --train-manifest data/manifests/train.jsonl \
  --validation-manifest data/manifests/validation.jsonl \
  --output configs/tuned_agent_config.json
```

For LayoutXLM/LayoutLMv2 fine-tuning, prepare word-level BIO labels with
normalized 0-1000 boxes, train a token-classification checkpoint, and place the
exported checkpoint locally at:

```text
models/
```

Expected optional checkpoint files are listed in the LayoutXLM section below.

## Data Management

This project is designed for public, synthetic, or anonymized document data.
Do not commit raw documents that contain names, addresses, phone numbers, tax
codes, emails, signatures, or other private information.

Expected data sources:

- Public OCR/document datasets such as SROIE for receipt information extraction.
- MC-OCR or equivalent Vietnamese receipt/invoice OCR datasets.
- Synthetic invoice templates for functional and smoke testing.
- Local private data only after removing or masking personally identifiable information.

Recommended data layout:

```text
data/
|-- raw/                  # Original local/private files, ignored by Git
|-- processed/            # Cleaned OCR-ready files, ignored by Git
|-- manifests/            # JSONL train/validation/test manifests
|-- sample_images/        # Small non-sensitive samples for smoke tests
`-- exported_document.*   # Generated exports, ignored by Git
```

Training and evaluation scripts expect JSONL manifests. One line represents one
document:

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

Recommended data split:

- Train: 70%
- Validation: 15%
- Test: 15%

Splits should be stratified by document type and language whenever possible.
Public invoice/receipt datasets may over-represent clean scans and
under-represent mobile photos, so blurred, skewed, Vietnamese, and dense-layout
samples should be included in evaluation.

## Evaluate

Run evaluation on a JSONL manifest:

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
- Per-document warnings and errors.

Manifest format is described in the Data Management section above.

## Optional LLM

The system works offline by default. To enable Groq/LLaMA support, create `api_key.env` in the project root:

```env
AI_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
LLM_MODEL=llama-3.3-70b-versatile
```

Restart the backend after editing the file. Do not commit `api_key.env`.

## Optional LayoutXLM

Place the fine-tuned checkpoint files directly inside:

```text
models/
```

The optional model directory is ignored by Git except for local files on your
machine. The project uses:

- `python-doctr` OCR detector: `db_resnet50`
- `python-doctr` OCR recognizer: `crnn_vgg16_bn`
- Optional fine-tuned LayoutXLM/LayoutLMv2 token classifier for invoices and receipts
- Optional Groq-hosted LLM for OCR correction, summarization, and document QA

Expected LayoutXLM/LayoutLMv2 checkpoint files:

- `config.json`
- `model.safetensors`
- `preprocessor_config.json`
- `sentencepiece.bpe.model`
- `special_tokens_map.json`
- `tokenizer_config.json`
- `tokenizer.json`
- `training_args.bin`

Configuration:

```env
LAYOUTXLM_ENABLED=true
LAYOUTXLM_MODEL_PATH=models
LAYOUTXLM_DEVICE=auto
LAYOUTXLM_MIN_CONFIDENCE=0.55
LAYOUTXLM_CHUNK_WORDS=180
```

Check status:

```text
GET http://localhost:8000/api/layoutxlm/status
```

LayoutLMv2/LayoutXLM visual backbone may require Detectron2 on Linux. If dependencies are missing, the backend still works and LayoutXLM reports `unavailable`.

### Install Detectron2 in Ubuntu WSL

Detectron2 is not officially convenient on native Windows. For LayoutXLM, run the backend inside Ubuntu WSL.

PowerShell, install and open Ubuntu if needed:

```powershell
wsl --install -d Ubuntu-22.04
wsl -d Ubuntu-22.04
```

Ubuntu terminal:

```bash
cd /mnt/d/ForCodeOnly/Document-Level-OCR-System
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-dev git build-essential ninja-build

python3 -m venv .venv-linux
source .venv-linux/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
python -c "import torch, torchvision; print(torch.__version__, torchvision.__version__)"
MAX_JOBS=2 python -m pip install --no-build-isolation "git+https://github.com/facebookresearch/detectron2.git"
```

Check Detectron2:

```bash
python -c "import detectron2; print('detectron2 ok')"
```

Run backend from Ubuntu WSL:

```bash
python -m uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

Keep the frontend running on Windows as usual:

```powershell
cd "D:\ForCodeOnly\Document-Level-OCR-System\UI\Data Export Interface"
npm.cmd run dev
```

## Monitoring and Logging

Monitoring endpoints:

- `GET /api/health`
- `GET /api/monitoring`
- `GET /api/metrics`

Tracked metrics:

- API request count.
- API error rate.
- Average, p50, p95, and max latency.
- OCR run count.
- Estimated OCR error rate before AI correction.
- Estimated OCR error rate after AI correction.
- LLM and LayoutXLM status.

The frontend has a `Giám sát` panel that refreshes every 5 seconds.

## Tests

```bash
python -m pytest -q
```

Current focused test suite covers:

- AI agent extraction and QA.
- Generic key-value extraction.
- Layout analysis.
- Table extraction.
- Reading order.
- Preprocessing.
- Monitoring quality estimation.

## Data and Privacy

- Do not commit private documents.
- Use public, synthetic, or anonymized data.
- Large datasets and checkpoints should be kept outside Git.
- `api_key.env`, `.env`, `models/` model files, generated exports, and temporary uploads are ignored.

## Deployment Limitations

- CPU OCR can be slow for large multi-page PDFs.
- LayoutXLM requires extra Linux dependencies.
- LLM usage adds network latency and privacy considerations.
- Monitoring is in-memory for this project version; production should export metrics to a persistent system.
