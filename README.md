# Document-Level-OCR-System

## Cách chạy web

Tải các thư viện Python:

```bash
pip install -r requirements.txt
```

Mở terminal thứ nhất tại thư mục chính và chạy frontend:

```bash
cd "UI\Data Export Interface"
npm run dev
```

Mở terminal thứ hai tại thư mục chính và chạy backend:

```bash
uvicorn src.app:app --reload
```

Mở web tại `http://localhost:5173/`.

## Bật LLM bổ trợ

Mặc định hệ thống chạy offline, không cần API key:

```bash
AI_PROVIDER=none
```

Nếu muốn bật Groq/LLaMA cho phần sửa OCR, tóm tắt và hỏi đáp tự do, tạo file `api_key.env` ở thư mục chính:

```env
AI_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
LLM_MODEL=llama-3.3-70b-versatile
```

Sau đó restart backend. Khi bật thành công, tab AI sẽ hiển thị trạng thái LLM, text đã sửa, field do LLM bổ sung và trace xử lý.

## Tiền xử lý ảnh OCR

Mặc định ảnh upload sẽ được tiền xử lý nhẹ trước khi đưa vào OCR:

```env
OCR_PREPROCESS_MODE=auto
```

Các chế độ hỗ trợ:

- `auto`: resize, tăng tương phản, khử nhiễu nhẹ, deskew nhẹ.
- `scan`: tối ưu ảnh scan đen trắng, có threshold.
- `camera`: tối ưu ảnh chụp điện thoại, giữ màu và xử lý nhẹ.
- `resize`: chỉ resize, không tăng tương phản/deskew.
- `none`: tắt tiền xử lý, dùng ảnh gốc.

Nếu muốn tắt để so sánh kết quả OCR, thêm vào `api_key.env` hoặc `.env`:

```env
OCR_PREPROCESS_MODE=none
```

## LayoutXLM bổ trợ trích xuất hóa đơn

Hệ thống tự tìm model đã fine-tune tại:

```text
model/layoutxlm-sroie-mcocr
```

LayoutXLM được lazy-load và chỉ chạy cho hóa đơn/biên lai. Model bổ sung các
trường `seller`, `seller_address`, `primary_date`, `total_amount`; các module
OCR, bảng, rule, generic KV và LLM vẫn được giữ nguyên.

Cấu hình tùy chọn:

```env
LAYOUTXLM_ENABLED=true
LAYOUTXLM_MODEL_PATH=model/layoutxlm-sroie-mcocr
LAYOUTXLM_DEVICE=auto
LAYOUTXLM_MIN_CONFIDENCE=0.55
LAYOUTXLM_CHUNK_WORDS=180
```

Kiểm tra trạng thái:

```text
GET http://localhost:8000/api/layoutxlm/status
```

Model hiện có kiến trúc LayoutLMv2 và cần Detectron2 cho visual backbone.
Nếu Detectron2 chưa được cài, backend vẫn hoạt động và LayoutXLM trả trạng thái
`unavailable` trong tab AI.
