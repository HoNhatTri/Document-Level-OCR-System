import kagglehub
import os
import shutil
import json
import re
from PIL import Image
from sklearn.model_selection import train_test_split

project_root = os.path.dirname(os.path.abspath(__file__))

data_vinai_dir = os.path.normpath(os.path.join(project_root, "..", "data", "vietnamese-ocr"))

doctr_dataset_dir = os.path.join(project_root, "..", "data", "doctr_dataset")
crop_output_dir = os.path.join(project_root, "..", "data", "cropped_images")

if os.path.exists(crop_output_dir): shutil.rmtree(crop_output_dir)
if os.path.exists(doctr_dataset_dir): shutil.rmtree(doctr_dataset_dir)
os.makedirs(crop_output_dir, exist_ok=True)

# Bộ từ vựng chuấn được sử dụng trong mô hình
VN_VOCAB = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝàáâãèéêìíòóôõùúýĂăĐđĨĩŨũƠơƯưẠạẢảẤấẦầẨẩẪẫẬậẮắẰằẲẳẴẵẶặẸẹẺẻẼẽẾếỀềỂểỄễỆệỈỉỊịỌọỎỏỐốỒồỔổỖỗỘộỚớỜờỞởỠỡỢợỤụỦủỨứỪừỬửỮữỰựỲỳỴỵỶỷỸỹ!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~° "

# ==========================================
# HÀM BỘ LỌC NHIỄU VÀ LÀM SẠCH VĂN BẢN CHUNG
# ==========================================
def is_valid_text(text):
    if not text or text in ["###"]: return False
    if not re.search(r'[a-zA-Z0-9À-ỹ]', text): return False
    return True

def clean_label(text):
    """
    Hàm làm sạch nhãn:
    1. Chuẩn hóa các dấu ngoặc/nháy dị thường.
    2. Sửa lỗi gõ nhầm ký tự tiếng Nga (Cyrillic) thành Latin.
    3. Lọc bỏ TẤT CẢ các ký tự không nằm trong VN_VOCAB.
    """
    # 1. Thay thế các ký tự lỗi phổ biến
    text = text.replace('с', 'c') # Đổi 'c' Nga thành 'c' Latin
    text = text.replace('а', 'a') # Đổi 'a' Nga thành 'a' Latin
    text = text.replace('о', 'o') # Đổi 'o' Nga thành 'o' Latin
    
    # 2. Lọc bỏ mọi ký tự lạ không có trong Vocab (Giúp chống Crash)
    cleaned_text = "".join([char for char in text if char in VN_VOCAB])
    
    # Trả về text đã xóa khoảng trắng thừa ở 2 đầu
    return cleaned_text.strip()


# ==========================================
# TẢI 2 TẬP DỮ LIỆU TỪ KAGGLE
# ==========================================
print("\n[+] Đang tải Dataset VinAI...")
if not os.path.exists(data_vinai_dir):
    path_vinai = kagglehub.dataset_download("trongnguyen04/vietnamese-ocr")
    shutil.copytree(path_vinai, data_vinai_dir, dirs_exist_ok=True)

all_crops = []
crop_id = 0
noise_count = 0

# ==========================================
# XỬ LÝ DATASET VinAI
# ==========================================
print("\n ĐANG CẮT ẢNH TỪ TẬP VINAI...")
labels_dir = os.path.join(data_vinai_dir, "labels")
image_folders = ["train_images", "test_image", "unseen_test_images"]

if os.path.exists(labels_dir):
    for label_file in os.listdir(labels_dir):
        if not label_file.endswith(".txt") or not label_file.startswith("gt_"): continue
        try: img_number = int(label_file.replace("gt_", "").replace(".txt", ""))
        except ValueError: continue
        
        img_name = f"im{img_number:04d}.jpg"
        img_path = next((os.path.join(data_vinai_dir, f, img_name) for f in image_folders if os.path.exists(os.path.join(data_vinai_dir, f, img_name))), None)
        
        if img_path:
            try: img = Image.open(img_path).convert("RGB")
            except Exception: continue
            
            with open(os.path.join(labels_dir, label_file), 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split(',', 8)
                    if len(parts) == 9:
                        try:
                            x1, y1, x2, y2, x3, y3, x4, y4 = map(int, map(float, parts[:8]))
                            text_label = parts[8].strip()
                            
                            if not is_valid_text(text_label):
                                noise_count += 1
                                continue
                                
                            if not text_label:
                                noise_count += 1
                                continue
                            
                            xmin, ymin = max(0, min(x1, x2, x3, x4)), max(0, min(y1, y2, y3, y4))
                            xmax, ymax = max(0, max(x1, x2, x3, x4)), max(0, max(y1, y2, y3, y4))
                            if xmax <= xmin or ymax <= ymin: continue
                            
                            crop_img = img.crop((xmin, ymin, xmax, ymax))
                            crop_filename = f"crop_vinai_{crop_id:06d}.jpg"
                            crop_filepath = os.path.join(crop_output_dir, crop_filename)
                            crop_img.save(crop_filepath)
                            
                            all_crops.append((crop_filepath, crop_filename, text_label))
                            crop_id += 1
                        except: pass

# ==========================================
# XỬ LÝ DỮ LIỆU & PHÂN CHIA (Train/Val/Test)
# ==========================================
total_images = len(all_crops)
print(f"\n[+] TỔNG KẾT: Cắt thành công {total_images} ảnh chữ SẠCH.")
print(f"[-] LOẠI BỎ: {noise_count} vùng chứa nhiễu hoặc chứa ký tự lạ.")

if total_images == 0:
    print("[LỖI] Không có ảnh nào. Vui lòng kiểm tra!")
    exit()

train_data, temp_data = train_test_split(all_crops, test_size=0.20, random_state=42)
val_data, test_data = train_test_split(temp_data, test_size=0.50, random_state=42)

def export_doctr_format(data_list, split_name):
    print(f" -> Đang xuất tập {split_name} ({len(data_list)} ảnh)...")
    split_dir = os.path.join(doctr_dataset_dir, split_name)
    os.makedirs(split_dir, exist_ok=True)
    
    labels_dict = {}
    for img_path, img_name, text_label in data_list:
        dst_path = os.path.join(split_dir, img_name)
        shutil.copy2(img_path, dst_path)
        labels_dict[img_name] = text_label
        
    with open(os.path.join(split_dir, "labels.json"), "w", encoding="utf-8") as f:
        json.dump(labels_dict, f, ensure_ascii=False, indent=4)

print("\nSao chép dữ liệu và tạo file labels.json...")
export_doctr_format(train_data, "train")
export_doctr_format(val_data, "val")
export_doctr_format(test_data, "test")

print(f"\n[+] Tập dữ liệu đã sẵn sàng tại: {doctr_dataset_dir}")