from __future__ import annotations
import json
import re
import os
from typing import Any
from groq import Groq

class DocumentExtractionAgent:
    """
    Hệ thống Agentic AI đa dụng.
    Trích xuất thông tin, sửa lỗi ký tự OCR NHƯNG GIỮ NGUYÊN CẤU TRÚC DÒNG/CỘT GỐC.
    """
    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            print("⚠️ CẢNH BÁO: Chưa có API_KEY trong môi trường.")
            
        self.client = Groq(api_key=api_key)
        self.model_name = "llama-3.3-70b-versatile"

    def _call_llm(self, prompt: str, require_json: bool = True) -> str:
        try:
            response = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a highly accurate Document Parsing AI. You always output valid JSON." if require_json else "You are a Document Parsing AI."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model=self.model_name,
                temperature=0.0, # Hạ temperature xuống 0 để LLM bớt "sáng tạo" và bám sát gốc hơn
                response_format={"type": "json_object"} if require_json else None
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Lỗi khi gọi Groq API: {str(e)}")
            return "{}" if require_json else ""

    def tool_number_format_validator(self, value: str) -> dict:
        if not value: return {"is_valid": True, "error": None}
        value_str = str(value)
        suspicious_patterns = [
            (r'\d+[oO]\d*', "Contains letter 'O' inside numbers"),
            (r'\d+[lI]\d*', "Contains letter 'l' or 'I' inside numbers"),
            (r'\d+[sS]\d*', "Contains letter 'S' inside numbers")
        ]
        for pattern, reason in suspicious_patterns:
            if re.search(pattern, value_str):
                return {"is_valid": False, "error": f"Possible OCR character confusion: {reason} in value '{value_str}'."}
        return {"is_valid": True, "error": None}

    def tool_semantic_syntax_checker(self, text_field: str) -> dict:
        """
        Kiểm tra các ký tự rác hoặc nhiễu.
        """
        if not text_field: return {"is_valid": True, "error": None}
        text = str(text_field).strip()
        
        # Bắt lỗi nhiễu OCR (các ký tự đặc biệt lặp lại vô lý)
        if re.search(r'([^\w\s.,!?:;\'"()\[\]{}])\1{4,}', text):
            return {"is_valid": False, "error": f"Excessive repeated symbols (scanning noise) found: '{text}'."}
            
        return {"is_valid": True, "error": None}

    def run_agentic_extraction(self, extracted_text: str) -> dict[str, Any]:
        trace_logs = []

        # BƯỚC 1: DRAFT EXTRACTION (Yêu cầu giữ nguyên Layout)
        prompt_1 = f"""
        You are an expert OCR parsing AI.
        Read the following raw OCR text. Extract ALL information and organize it into a JSON object with dynamic keys.
        
        CRUCIAL REQUIREMENT FOR "full_corrected_text": 
        You MUST include a root-level key named "full_corrected_text". 
        This key must contain the corrected version of the OCR text but you MUST STRICTLY PRESERVE the original layout, line breaks (\\n), empty lines, and spatial arrangement of the text.
        - ONLY fix spelling mistakes and OCR character recognition errors (e.g., confusing '0' and 'O', '1' and 'l').
        - Remove random scanning noise (e.g., '7 qum L a').
        - DO NOT merge broken lines into continuous sentences. Keep the line breaks exactly as they appear in the raw text.
        - DO NOT change the order of the text.

        Raw OCR Text:
        {extracted_text[:4000]}
        """
        draft_response = self._call_llm(prompt_1, require_json=True)
        
        try:
            draft_fields = json.loads(draft_response)
            trace_logs.append(f"Layout-Preserving Draft extraction completed using {self.model_name}.")
        except Exception as e:
            draft_fields = {}
            trace_logs.append(f"Failed to parse initial LLM JSON. Error: {str(e)}")

        # BƯỚC 2: QUÉT LỖI ĐỆ QUY
        errors_found = []
        def scan_errors(data, path="root"):
            if isinstance(data, dict):
                for k, v in data.items(): scan_errors(v, f"{path} -> '{k}'")
            elif isinstance(data, list):
                for i, v in enumerate(data): scan_errors(v, f"{path}[{i}]")
            elif isinstance(data, str):
                if any(char.isdigit() for char in data):
                    num_check = self.tool_number_format_validator(data)
                    if not num_check["is_valid"]:
                        errors_found.append(f"Location [{path}]: {num_check['error']}")
                        trace_logs.append(f"Number Tool flagged issue at {path}.")
                sem_check = self.tool_semantic_syntax_checker(data)
                if not sem_check["is_valid"]:
                    errors_found.append(f"Location [{path}]: {sem_check['error']}")
                    trace_logs.append(f"Noise Tool flagged issue at {path}.")

        scan_errors(draft_fields)
        final_fields = draft_fields.copy()

        # BƯỚC 3: TỰ SỬA LỖI NẾU CẦN
        if errors_found:
            trace_logs.append(f"Decision -> Found {len(errors_found)} OCR errors. Triggering Self-Correction Node.")
            error_prompt = "\n".join(errors_found)
            
            prompt_2 = f"""
            The initial extraction contained these OCR errors:
            {error_prompt}
            
            Original OCR Text:
            {extracted_text[:4000]}
            
            Return the fully corrected JSON object. 
            CRITICAL: You MUST keep and update the "full_corrected_text" key. Fix the reported character errors but STRICTLY PRESERVE the exact original line breaks (\\n), spacing, and structural layout of the text. DO NOT merge lines.
            """
            corrected_response = self._call_llm(prompt_2, require_json=True)
            try:
                final_fields = json.loads(corrected_response)
                trace_logs.append(f"Self-Correction successful.")
            except Exception as e:
                trace_logs.append(f"Self-Correction failed. Error: {str(e)}")
        else:
            trace_logs.append("Decision -> No character/noise errors detected. Proceeding with draft.")

        full_corrected_text = final_fields.get("full_corrected_text", "")
        if "full_corrected_text" in final_fields:
            del final_fields["full_corrected_text"]

        return {
            "document_type": "universal_document",
            "document_type_confidence": 1.0,
            "full_corrected_text": full_corrected_text,
            "fields": self._format_for_frontend(final_fields),
            "agent_trace": trace_logs,
            "summary": "Layout-Preserving Extraction completed."
        }

    def _format_for_frontend(self, fields: dict) -> dict:
        formatted = {}
        for key, value in fields.items():
            formatted[key] = {
                "value": value,
                "confidence": 0.95,
                "source": "agentic_llm_extraction",
            }
        return formatted

    def analyze(self, extracted_text: str, **kwargs) -> dict[str, Any]:
        if not extracted_text.strip():
            return {
                "document_type": "unknown",
                "document_type_confidence": 0.0,
                "full_corrected_text": "",
                "fields": {},
                "agent_trace": ["Text is empty. Extraction aborted."],
                "summary": "No text found in document."
            }
        return self.run_agentic_extraction(extracted_text)