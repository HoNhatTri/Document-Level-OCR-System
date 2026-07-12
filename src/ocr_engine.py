import os
import yaml
import torch

from doctr.io import DocumentFile
from doctr.models import ocr_predictor
from doctr import models as doctr_models

# Import các module tiền xử lý từ file của bạn bạn
from src.preprocess import ImagePreprocessor
from src.reading_order import bounding_boxes_from_structured, raw_text_from_structured


class OCREngine:
    def __init__(self, config_path="configs/model_config.yaml"):
        """Initialize the OCR model from the YAML config."""
        
        # Đọc cấu hình từ file YAML
        with open(config_path, "r", encoding="utf-8") as file:
            config = yaml.safe_load(file)["ocr"]

        print("[*] Dang tai mo hinh OCR...")
        print(f"    - Detector: {config['detector']}")
        print(f"    - Recognizer: {config['recognizer']}")

        custom_weights_path = config.get('custom_weights')
        custom_vocab = config.get('custom_vocab')
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Khởi tạo mô hình
        if custom_weights_path and os.path.exists(custom_weights_path) and custom_vocab:
            print(f"    -> [INFO] Phat hien trong so tuy chinh tai: {custom_weights_path}")
            
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
            print("    -> [INFO] Da nap thanh cong bo nhan dien Tieng Viet!")
            
        else:
            # Fallback về mặc định nếu không có file weights
            print("    -> [WARNING] Khong dung trong so tuy chinh, tai ban mac dinh.")
            self.model = ocr_predictor(
                det_arch=config["detector"],
                reco_arch=config["recognizer"],
                pretrained=config["pretrained"],
            )

        self.model.to(device)
        
        # 3. KHỞI TẠO TIỀN XỬ LÝ (Logic của bạn bạn)
        self.preprocessor = ImagePreprocessor()
        self.last_document_images = []
        print("[+] Khoi tao bo may OCR thanh cong!\n")

    def process_document(self, file_path):
        """Read an image/PDF file and run OCR."""
        self._reset_processing_info()
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Khong tim thay file: {file_path}")

        extension = os.path.splitext(file_path)[1].lower()
        
        # Xử lý PDF
        if extension == ".pdf":
            doc = DocumentFile.from_pdf(file_path)
            self.last_document_images = list(doc)
            return self.model(doc)
            
        # Xử lý Ảnh
        elif extension in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}:
            return self._process_image_file(file_path)
        else:
            raise ValueError(f"Dinh dang file khong duoc ho tro: {extension}")

    def _process_image_file(self, file_path):
        """Luồng tiền xử lý ảnh riêng biệt (Xoay ảnh xéo, làm nét...)"""
        ocr_image_path = file_path
        self.current_processed_image_path = file_path
        
        temp_preprocessed_path = None

        if self.preprocessor.should_preprocess(file_path):
            try:
                temp_preprocessed_path = self.preprocessor.preprocess_to_temp_file(file_path)
                ocr_image_path = temp_preprocessed_path
                
                self.current_processed_image_path = temp_preprocessed_path 
                
                info = self.get_processing_info()
                
                if info.get("special_handling"):
                    print(f"[*] Da xu ly rieng anh xeo: {info}")
                else:
                    print(f"[*] Da tien xu ly anh OCR: {self.preprocessor.mode}")
                    
            except Exception as exc:
                self._reset_processing_info()
                print(f"[!] Bo qua tien xu ly anh, dung anh goc. Ly do: {exc}")

        doc = DocumentFile.from_images(ocr_image_path)
        self.last_document_images = list(doc)
        return self.model(doc)

    def process_image(self, image_path):
        """Đọc ảnh từ đường dẫn và thực hiện nhận diện."""
        return self.process_document(image_path)

    def get_raw_text(self, result, structured_data=None):
        """Trích xuất văn bản thuần túy (Kết hợp logic xếp dòng thông minh)."""
        structured = structured_data if structured_data is not None else result.export()
        
        # Nếu ảnh bị xéo và đã được căn chỉnh, dùng thuật toán sắp xếp dòng
        if self._uses_special_handling(structured):
            ordered_text = raw_text_from_structured(structured)
            if ordered_text:
                return ordered_text

        # Trích xuất văn bản bình thường
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

    def get_bounding_boxes(self, structured_data):
        """Return line boxes. Keep normal docTR order unless skew handling is enabled."""
        if self._uses_special_handling(structured_data):
            return bounding_boxes_from_structured(structured_data)
        return self._default_bounding_boxes(structured_data)

    # ==========================================
    # CÁC HÀM TIỆN ÍCH QUẢN LÝ TRẠNG THÁI (State Management)
    # ==========================================
    def get_processing_info(self):
        return dict(getattr(self.preprocessor, "last_info", {}) or {})

    def take_document_images(self):
        images = self.last_document_images
        self.last_document_images = []
        return images

    def _reset_processing_info(self):
        self.last_document_images = []
        self.preprocessor.last_info = {
            "skew_detected": False,
            "skew_angle": None,
            "page_rectified": False,
            "special_handling": False,
        }

    def _uses_special_handling(self, structured_data):
        processing = structured_data.get("_processing", {}) if isinstance(structured_data, dict) else {}
        return bool(processing.get("special_handling"))

    def _default_bounding_boxes(self, structured_data):
        boxes = []
        box_id = 1
        for page in structured_data.get("pages", []):
            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    text_val = " ".join(
                        word.get("value", "")
                        for word in line.get("words", [])
                        if word.get("value")
                    ).strip()
                    
                    if not text_val:
                        continue

                    geom = line.get("geometry", [[0, 0], [1, 1]])
                    xmin, ymin = geom[0]
                    xmax, ymax = geom[1]
                    boxes.append(
                        {
                            "id": str(box_id),
                            "x": xmin * 100,
                            "y": ymin * 100,
                            "width": (xmax - xmin) * 100,
                            "height": (ymax - ymin) * 100,
                            "label": text_val,
                            "type": "text",
                        }
                    )
                    box_id += 1
        return boxes