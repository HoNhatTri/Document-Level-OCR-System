import yaml
import os
import torch
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
from doctr import models as doctr_models

class OCREngine:
    def __init__(self, config_path="configs/model_config.yaml"):
        """Khởi tạo mô hình OCR dựa trên file cấu hình."""
        # Đọc cấu hình từ file YAML
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)['ocr']
        
        print(f"[*] Đang tải mô hình OCR...")
        print(f"    - Detector: {config['detector']}")
        print(f"    - Recognizer: {config['recognizer']}")

        custom_weights_path = config.get('custom_weights')
        custom_vocab = config.get('custom_vocab')
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        if custom_weights_path and os.path.exists(custom_weights_path) and custom_vocab:
            print(f"    -> [INFO] Phát hiện trọng số tùy chỉnh tại: {custom_weights_path}")
            
            recognizer_name = config['recognizer']
            model_constructor = getattr(doctr_models, recognizer_name)
            custom_reco_model = model_constructor(pretrained=False, vocab=custom_vocab)
            
            state_dict = torch.load(custom_weights_path, map_location=device)
            custom_reco_model.load_state_dict(state_dict)
            custom_reco_model.to(device)
            custom_reco_model.eval()
            
            self.model = ocr_predictor(
                det_arch=config['detector'],
                reco_arch=custom_reco_model, 
                pretrained=True
            )
            print("    -> [INFO] Đã nạp thành công bộ nhận diện Tiếng Việt!")
            
        else:
            # Nếu không tìm thấy file .pt, fallback về mô hình mặc định của docTR
            print("    -> [WARNING] Không dùng trọng số tùy chỉnh, tải bản mặc định.")
            self.model = ocr_predictor(
                det_arch=config['detector'],
                reco_arch=config['recognizer'],
                pretrained=config['pretrained']
            )
        
        # Khởi tạo docTR với các kiến trúc đã chọn trong config
        self.model.to(device)
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
