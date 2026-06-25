import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

class TextCorrector:
    def __init__(self, model_id="protonx-models/protonx-legal-tc"):
        """Khởi tạo mô hình seq2seq để sửa lỗi chính tả/ngữ nghĩa tiếng Việt."""
        print(f"[*] Đang tải mô hình Text Correction: {model_id}...")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        try:
            # Tải Tokenizer và Model
            self.tokenizer = AutoTokenizer.from_pretrained(model_id)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(model_id).to(self.device)
            self.model.eval()
            print("[+] Khởi tạo mô hình Text Correction thành công!\n")
            self.enabled = True
        except Exception as e:
            print(f"[!] Lỗi tải mô hình: {e}")
            self.enabled = False

    def correct_sentence(self, sentence: str) -> str:
        """Thực hiện hiệu đính trên một câu duy nhất."""
        if not self.enabled or not sentence.strip():
            return sentence
            
        inputs = self.tokenizer(sentence, return_tensors="pt", max_length=512, truncation=True).to(self.device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs, 
                max_length=512,
                num_beams=4, # Beam search để đưa ra kết quả dịch/sửa lỗi mượt nhất
                early_stopping=True
            )
            
        return self.tokenizer.decode(outputs[0], skip_special_tokens=True)

    def correct_document(self, raw_text: str) -> str:
        """
        Nhận toàn bộ văn bản từ OCR, tách thành từng dòng, 
        sửa lỗi cho từng dòng và gộp lại để không làm hỏng format (xuống dòng).
        """
        if not self.enabled or not raw_text.strip():
            return raw_text
            
        lines = raw_text.split('\n')
        corrected_lines = []
        
        for line in lines:
            if line.strip():
                corrected = self.correct_sentence(line)
                corrected_lines.append(corrected)
            else:
                # Giữ nguyên các khoảng trắng / dòng trống để bảo toàn bố cục
                corrected_lines.append("")
                
        return "\n".join(corrected_lines)