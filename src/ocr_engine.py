import yaml
import os
from doctr.io import DocumentFile
from doctr.models import ocr_predictor

class OCREngine:
    def __init__(self, config_path="configs/model_config.yaml"):
        """Khởi tạo mô hình OCR dựa trên file cấu hình."""
        # Đọc cấu hình từ file YAML
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)['ocr']
        
        print(f"[*] Đang tải mô hình OCR...")
        print(f"    - Detector: {config['detector']}")
        print(f"    - Recognizer: {config['recognizer']}")
        
        # Khởi tạo docTR với các kiến trúc đã chọn trong config
        self.model = ocr_predictor(
            det_arch=config['detector'],
            reco_arch=config['recognizer'],
            pretrained=config['pretrained']
        )
        print("[+] Khởi tạo mô hình thành công!\n")

    def process_document(self, file_path):
        """Read an image/PDF file and run OCR."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Khong tim thay file: {file_path}")

        extension = os.path.splitext(file_path)[1].lower()
        if extension == ".pdf":
            doc = DocumentFile.from_pdf(file_path)
        elif extension in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}:
            doc = DocumentFile.from_images(file_path)
        else:
            raise ValueError(f"Dinh dang file khong duoc ho tro: {extension}")

        result = self.model(doc)
        return result

    def process_image(self, image_path):
        """Đọc ảnh từ đường dẫn và thực hiện nhận diện."""
        return self.process_document(image_path)

    def get_raw_text(self, result):
        """Trích xuất văn bản thuần túy từ kết quả nhận diện (dùng cho LLM/Agent)."""
        text = ""
        for page in result.pages:
            for block in page.blocks:
                for line in block.lines:
                    line_text = " ".join([word.value for word in line.words])
                    text += line_text + "\n"
                text += "\n"
        return text.strip()
    
    def get_structured_data(self, result):
        """Xuất toàn bộ cấu trúc (bao gồm tọa độ bounding box) ra dạng Dictionary (JSON)."""
        return result.export()
