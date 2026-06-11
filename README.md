# Document-Level-OCR-System-
-
-
-
## Hướng dẫn cách chạy web
- Đầu tiên chạy lệnh sau để tải các thư viện cần thiết:
```bash
pip install -r requirements.txt
```
- Mở terminal thứ nhất tại thư mục chính, lần lượt chạy các lệnh cho phần FE:
```bash
cd '.\UI\Data Export Interface\'
npm run dev
```
- Mở terminal thứ hai tại thư mục chính, chạy lệnh sau cho BE:
```bash
uvicorn src.app:app --reload
``` 
- Mở trang web lại địa chỉ `http://localhost:5173/`


