from datasets import load_dataset

# Tải tập dữ liệu
dataset = load_dataset("niits/vietnamese-legal-ocr")

# Truy cập vào dữ liệu (ví dụ: tập train)
for item in dataset['train']:
    image = item['image']  # Dữ liệu ảnh
    text = item['text']    # Nhãn văn bản tương ứng
    print(f"Text: {text}")