import os
import json
import sys
from dotenv import load_dotenv

load_dotenv(dotenv_path="api_key.env")

# 1. CẤU HÌNH ĐƯỜNG DẪN THƯ MỤC GỐC
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)


from src.ocr_engine import OCREngine
from src.agent import DocumentExtractionAgent

def main():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or not api_key.startswith("gsk_"):
        print("[-] CẢNH BÁO: API Key chưa đúng định dạng.")
        return

    image_path = os.path.join(project_root, "data", "sample_images", "test_2.jpg")
    config_path = os.path.join(project_root, "configs", "model_config.yaml")
    
    if not os.path.exists(image_path):
        print(f"[-] Không tìm thấy ảnh tại: {image_path}")
        return

    print("[1] Đang khởi tạo mô hình OCR...")
    ocr = OCREngine(config_path=config_path)
    
    print(f"[2] Đang đọc ảnh và trích xuất văn bản từ: {image_path}...\n")
    result = ocr.process_image(image_path)
    extracted_text = ocr.get_raw_text(result)
    
    print("="*60)
    print(" 📄 VĂN BẢN OCR THÔ (BỊ NHIỄU, ĐỨT GÃY TỪ ẢNH GỐC):")
    print("="*60)
    print(extracted_text[:1000] + "\n...\n") 

    print("[3] Kích hoạt Agentic AI (Groq - LLaMA 3.3) để phân tích và tự sửa lỗi...\n")
    agent = DocumentExtractionAgent()
    analysis_result = agent.analyze(extracted_text)

    # ---------------------------------------------------------
    # IN PHẦN MỚI DÀNH RIÊNG CHO WEB DEMO CỦA BẠN
    # ---------------------------------------------------------
    print("="*60)
    print(" ✨ VĂN BẢN ĐÃ ĐƯỢC LLM SỬA LỖI:")
    print("="*60)
    print(analysis_result.get("full_corrected_text", "Không có văn bản nào được trả về."))
    print("\n")

    print("="*60)
    print(" 📊 DỮ LIỆU JSON ĐÃ ĐƯỢC BÓC TÁCH (DYNAMIC FIELDS):")
    print("="*60)
    print(json.dumps(analysis_result.get("fields", {}), indent=2, ensure_ascii=False))
    print("\n")

    print("="*60)
    print(" 🤖 AGENT TRACE (NHẬT KÝ KIỂM TRA LỖI):")
    print("="*60)
    for step in analysis_result.get("agent_trace", []):
        print(f"  • {step}")
    print("="*60)

if __name__ == "__main__":
    main()