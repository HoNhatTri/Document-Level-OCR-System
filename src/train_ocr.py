import os
import time
import torch
import matplotlib.pyplot as plt
from torch.utils.data import DataLoader
from doctr.datasets import RecognitionDataset
from doctr.models import crnn_vgg16_bn
from doctr.transforms import Resize

# ==========================================
# 1. CẤU HÌNH SIÊU THAM SỐ
# ==========================================
BATCH_SIZE = 16
EPOCHS = 10
LEARNING_RATE = 1e-4
WEIGHT_DECAY = 1e-5

# Bộ từ vựng Tiếng Việt đầy đủ (Bắt buộc phải có để model học được dấu)
VN_VOCAB = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝàáâãèéêìíòóôõùúýĂăĐđĨĩŨũƠơƯưẠạẢảẤấẦầẨẩẪẫẬậẮắẰằẲẳẴẵẶặẸẹẺẻẼẽẾếỀềỂểỄễỆệỈỉỊịỌọỎỏỐốỒồỔổỖỗỘộỚớỜờỞởỠỡỢợỤụỦủỨứỪừỬửỮữỰựỲỳỴỵỶỷỸỹ!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~ "

# ==========================================
# 2. THIẾT LẬP ĐƯỜNG DẪN
# ==========================================
project_root = os.path.dirname(os.path.abspath(__file__))
train_dir = os.path.normpath(os.path.join(project_root, "..", "data", "doctr_dataset", "train"))
val_dir = os.path.normpath(os.path.join(project_root, "..", "data", "doctr_dataset", "val"))

models_dir = os.path.normpath(os.path.join(project_root, "..", "models"))
os.makedirs(models_dir, exist_ok=True)

# ==========================================
# 3. CHUẨN BỊ DATALOADER
# ==========================================
print("[1/5] Đang nạp dữ liệu huấn luyện...")

resize_transform = Resize((32, 128))

train_set = RecognitionDataset(img_folder=train_dir, labels_path=os.path.join(train_dir, "labels.json"),img_transforms=resize_transform)
val_set = RecognitionDataset(img_folder=val_dir, labels_path=os.path.join(val_dir, "labels.json"),img_transforms=resize_transform)

def collate_fn(samples):
    images, targets = zip(*samples)
    images = torch.stack(images, dim=0)
    return images, list(targets)

train_loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True, collate_fn=collate_fn)
val_loader = DataLoader(val_set, batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_fn)

# ==========================================
# 4. KHỞI TẠO MÔ HÌNH
# ==========================================
print("\n[2/5] Khởi tạo mô hình CRNN-VGG16 với từ vựng Tiếng Việt...")
model = crnn_vgg16_bn(pretrained=True, vocab=VN_VOCAB)

if torch.cuda.device_count() > 1:
    model = torch.nn.DataParallel(model)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
print(f"-> Thiết bị đang sử dụng: {device}")

optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)

# ==========================================
# 5. VÒNG LẶP HUẤN LUYỆN (TRAINING LOOP)
# ==========================================
print(f"\n[3/5] Bắt đầu huấn luyện ({EPOCHS} Epochs)...")
train_loss_history = []
val_loss_history = []

for epoch in range(EPOCHS):
    start_time = time.time()
    
    model.train()
    total_train_loss = 0.0
    
    for batch_idx, (images, targets) in enumerate(train_loader):
        images = images.to(device)
        
        optimizer.zero_grad()
        out = model(images, return_model_output=True, return_preds=False)
        logits = out.get('out_map', out.get('logits'))

        if isinstance(model, torch.nn.DataParallel):
            loss = model.module.compute_loss(logits, targets)
        else:
            loss = model.compute_loss(logits, targets)
        
        loss.backward()
        optimizer.step()
        
        total_train_loss += loss.item()
        
        if batch_idx % 10 == 0:
            print(f"   Epoch {epoch+1}/{EPOCHS} | Batch {batch_idx}/{len(train_loader)} | Loss: {loss.item():.4f}")
            
    avg_train_loss = total_train_loss / len(train_loader)
    train_loss_history.append(avg_train_loss)
    
    # --- Bước Kiểm Định (Validation) ---
    model.eval()
    total_val_loss = 0.0
    
    with torch.no_grad():
        for images, targets in val_loader:
            images = images.to(device)
            out = model(images, return_model_output=True, return_preds=False)
            logits = out.get('out_map', out.get('logits'))

            if isinstance(model, torch.nn.DataParallel):
                loss = model.module.compute_loss(logits, targets)
            else:
                loss = model.compute_loss(logits, targets)

            total_val_loss += loss.item()
            
    avg_val_loss = total_val_loss / len(val_loader)
    val_loss_history.append(avg_val_loss)
    
    time_taken = time.time() - start_time
    print(f"==> Kết thúc Epoch {epoch+1} | Tgian: {time_taken:.0f}s | Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f}\n")

# ==========================================
# 6. LƯU MÔ HÌNH VÀ VẼ BIỂU ĐỒ BÁO CÁO
# ==========================================
print("[4/5] Đang lưu mô hình...")
model_save_path = os.path.join(models_dir, "vietnamese_crnn_vgg16.pt")
torch.save(model.state_dict(), model_save_path)
print(f"-> Mô hình đã lưu tại: {model_save_path}")

print("[5/5] Đang vẽ biểu đồ báo cáo...")
plt.figure(figsize=(10, 6))
plt.plot(range(1, EPOCHS + 1), train_loss_history, label='Train Loss', marker='o')
plt.plot(range(1, EPOCHS + 1), val_loss_history, label='Validation Loss', marker='s')
plt.title('Quá trình huấn luyện mô hình CRNN-VGG16 (Tiếng Việt)')
plt.xlabel('Epochs')
plt.ylabel('Loss (Cross Entropy)')
plt.legend()
plt.grid(True)

chart_save_path = os.path.join(models_dir, "loss_curve.png")
plt.savefig(chart_save_path)
print(f"-> Biểu đồ đã được lưu tại: {chart_save_path}")

print("\nHOÀN TẤT QUÁ TRÌNH HUẤN LUYỆN!")