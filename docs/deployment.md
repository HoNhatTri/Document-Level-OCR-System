# Deployment

## Deployment Method

The system supports:

- REST API with FastAPI.
- Web demo with React/Vite.
- Docker Compose deployment for backend and frontend.

## Local Development

Backend:

```bash
python -m pip install -r requirements.txt
python -m uvicorn src.app:app --reload
```

Frontend:

```bash
cd "UI/Data Export Interface"
npm install
npm run dev
```

## Docker

```bash
docker compose up --build
```

Services:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Health: `GET /api/health`
- Monitoring: `GET /api/monitoring`

## Ubuntu WSL Backend for LayoutXLM

LayoutXLM/LayoutLMv2 requires Detectron2 for the visual backbone. The recommended local setup is to run the backend inside Ubuntu WSL and keep the frontend on Windows.

PowerShell:

```powershell
wsl --install -d Ubuntu-22.04
wsl -d Ubuntu-22.04
```

Ubuntu:

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
python -c "import detectron2; print('detectron2 ok')"
```

Run backend in Ubuntu:

```bash
python -m uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

Run frontend in Windows PowerShell:

```powershell
cd "D:\ForCodeOnly\Document-Level-OCR-System\UI\Data Export Interface"
npm.cmd run dev
```

## Input Formats

Supported uploads:

- PDF
- PNG
- JPG/JPEG

## Output Formats

API returns:

- Raw OCR text.
- Structured OCR JSON.
- Bounding boxes.
- Detected tables.
- Layout regions.
- AI analysis with document type, fields, summary, warnings, LLM/LayoutXLM status.

Export endpoints:

- `POST /api/export-pdf`
- `POST /api/export-docx`

## Latency and Scalability

Latency drivers:

- Image size and page count.
- OCR model inference.
- Optional LayoutXLM inference.
- Optional remote LLM call.

Scalability strategy:

- Keep OCR backend stateless.
- Run multiple backend replicas behind a load balancer.
- Store uploaded files in object storage for production.
- Move long multi-page OCR jobs to a queue if needed.

## Model Versioning

Recommended versioning:

- Store OCR config in `configs/model_config.yaml`.
- Store LayoutXLM checkpoints in an external model registry.
- Record model path, model hash, training dataset version, and evaluation metrics.
- Expose active model status through `/api/layoutxlm/status` and `/api/monitoring`.

## Deployment Challenges

- LayoutLMv2/LayoutXLM may require Detectron2 in Linux.
- Large checkpoints should not be included in Docker image layers.
- LLM API keys must be stored outside Git.
- CPU inference can be slow for large PDFs.
