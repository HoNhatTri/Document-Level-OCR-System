from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import shutil
import os
from src.ocr_engine import OCREngine
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from docx import Document
from docx.shared import Inches, Pt

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = OCREngine(config_path="configs/model_config.yaml")

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    temp_file_path = f"data/sample_images/temp_{file.filename}"
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    raw_result = engine.process_image(temp_file_path)
    extracted_text = engine.get_raw_text(raw_result)
    structured_data = engine.get_structured_data(raw_result)
    
    # --- ĐOẠN CODE MỚI THÊM: Tính toán tọa độ Bounding Box ---
    bounding_boxes = []
    box_id = 1
    
    pages = structured_data.get("pages", [])
    for page in pages:
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                # Lấy nội dung của cả dòng
                text_val = " ".join([w.get("value", "") for w in line.get("words", [])]).strip()
                if not text_val:
                    continue
                
                # Lấy tọa độ (docTR trả về tỷ lệ từ 0 đến 1)
                geom = line.get("geometry", [[0,0], [1,1]])
                xmin, ymin = geom[0]
                xmax, ymax = geom[1]
                
                # Quy đổi sang % (0-100) để Frontend vẽ CSS chính xác
                bounding_boxes.append({
                    "id": str(box_id),
                    "x": xmin * 100,
                    "y": ymin * 100,
                    "width": (xmax - xmin) * 100,
                    "height": (ymax - ymin) * 100,
                    "label": text_val,
                    "type": "text"
                })
                box_id += 1
                
    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)
        
    return {
        "status": "success",
        "filename": file.filename,
        "extracted_text": extracted_text,
        "json_data": structured_data,
        "bounding_boxes": bounding_boxes # <--- Truyền mảng tọa độ này lên Web
    }

@app.post("/api/export-pdf")
async def export_pdf(data: dict):
    pdf_path = "data/exported_document.pdf"
    c = canvas.Canvas(pdf_path, pagesize=A4)
    page_width, page_height = A4
    font_name = 'Times-Roman' 

    pages = data.get("pages", [])
    for page in pages:
        all_lines = []
        
        # Trích xuất theo cấp độ DÒNG (Line) để giữ font chữ đều tăm tắp
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                words = line.get("words", [])
                if not words: continue
                
                # Nối các từ lại thành dòng hoàn chỉnh
                text_val = " ".join([w.get("value", "") for w in words]).strip()
                geom = line.get("geometry", [[0,0], [1,1]])
                xmin, ymin = geom[0]
                xmax, ymax = geom[1]
                
                all_lines.append({
                    "text": text_val,
                    "xmin": xmin,
                    "ymin": ymin,
                    "ymax": ymax
                })
        
        # Sắp xếp các dòng để copy/paste không bị ngược thứ tự
        all_lines.sort(key=lambda l: (round(l['ymin'] * 100), l['xmin']))
        
        # Vẽ PDF
        for l in all_lines:
            x = l['xmin'] * page_width
            y = page_height - (l['ymin'] * page_height)
            box_height = (l['ymax'] - l['ymin']) * page_height
            
            # Ép font size cố định cho cả dòng
            font_size = max(8, box_height * 0.8) 
            
            c.setFont(font_name, font_size)
            c.drawString(x, y - font_size, l['text'])
            
        c.showPage()
        
    c.save()
    return FileResponse(pdf_path, media_type="application/pdf", filename="exported_document.pdf")


@app.post("/api/export-docx")
async def export_docx(data: dict):
    docx_path = "data/exported_document.docx"
    doc = Document()
    
    pages = data.get("pages", [])
    for page_idx, page in enumerate(pages):
        all_lines = []
        
        # Trích xuất theo cấp độ Dòng
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                words = line.get("words", [])
                if not words: continue
                
                text_val = " ".join([w.get("value", "") for w in words]).strip()
                geom = line.get("geometry", [[0,0], [1,1]])
                xmin, ymin = geom[0]
                
                all_lines.append({
                    "text": text_val,
                    "xmin": xmin,
                    "ymin": ymin
                })
        
        # Sắp xếp từ trên xuống dưới, trái qua phải
        all_lines.sort(key=lambda l: (round(l['ymin'] * 100), l['xmin']))
        
        for l in all_lines:
            p = doc.add_paragraph()
            
            # ĐÂY LÀ CHÌA KHÓA: 
            # Chiều rộng trang DOCX thực tế (trừ margin) khoảng ~6.5 inches. 
            # Ta nhân tọa độ X (từ 0 đến 1) với 6.5 để đẩy chữ vào đúng vị trí.
            indent_inches = l['xmin'] * 6.5
            p.paragraph_format.left_indent = Inches(indent_inches)
            
            # Thu hẹp khoảng cách giữa các đoạn để giống tài liệu thật
            p.paragraph_format.space_after = Pt(2)
            
            run = p.add_run(l['text'])
            run.font.name = 'Arial'
            run.font.size = Pt(10)
            
        # Thêm trang mới nếu ảnh có nhiều trang
        if page_idx < len(pages) - 1:
            doc.add_page_break()
            
    doc.save(docx_path)
    return FileResponse(
        docx_path, 
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
        filename="exported_document.docx"
    )