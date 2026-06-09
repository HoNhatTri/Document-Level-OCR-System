import sys
import os

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Thêm thư mục gốc vào đường dẫn hệ thống để có thể import từ thư mục src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ocr_engine import OCREngine

def main():
    # 1. Khởi tạo engine
    engine = OCREngine(config_path="configs/model_config.yaml")
    
    # 2. Định nghĩa ảnh đầu vào
    sample_img = "data/sample_images/test.jpg" # Thay tên file nếu cần
    
    if not os.path.exists(sample_img):
        print(f"[-] Lỗi: Hãy thêm một ảnh vào {sample_img} để test.")
        return

    # 3. Chạy xử lý
    print(f"[*] Đang xử lý ảnh: {sample_img}")
    result = engine.process_image(sample_img)
    
    # 4. Lấy kết quả Text thuần
    extracted_text = engine.get_raw_text(result)
    
    print("\n" + "="*40)
    print(" KẾT QUẢ VĂN BẢN (RAW TEXT)")
    print("="*40)
    print(extracted_text)
    print("="*40)

    # (Tùy chọn) Hiển thị trực quan bounding box trên ảnh
    # result.show()

if __name__ == "__main__":
    main()