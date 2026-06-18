from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


class OptionalLLMAgent:
    """Optional LLM helper used as a supplement to deterministic extraction.

    The main OCR pipeline must keep working without an API key or the Groq
    package installed. This class therefore reports a status payload instead
    of raising during app startup.
    """

    DISABLED_PROVIDERS = {"", "0", "false", "none", "off", "disabled"}

    def __init__(self):
        self._load_env_file("api_key.env")
        self._load_env_file(".env")

        self.provider = os.getenv("AI_PROVIDER", os.getenv("LLM_PROVIDER", "none")).strip().lower()
        self.model_name = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile").strip()
        self.max_chars = self._int_env("LLM_MAX_CHARS", 6000)
        self.client = None
        self.disabled_reason = ""

        if self.provider in self.DISABLED_PROVIDERS:
            self.provider = "none"
            self.disabled_reason = "LLM is disabled. Set AI_PROVIDER=groq and GROQ_API_KEY to enable it."
            return

        if self.provider != "groq":
            self.disabled_reason = f"Unsupported AI_PROVIDER '{self.provider}'. Only 'groq' is supported now."
            return

        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            self.disabled_reason = "Missing GROQ_API_KEY."
            return

        try:
            from groq import Groq
        except ImportError:
            self.disabled_reason = "Package 'groq' is not installed. Run pip install -r requirements.txt."
            return

        self.client = Groq(api_key=api_key)

    @property
    def enabled(self) -> bool:
        return self.provider == "groq" and self.client is not None

    def status(self) -> dict[str, Any]:
        if self.enabled:
            return {
                "status": "enabled",
                "provider": self.provider,
                "model": self.model_name,
                "message": "LLM supplement is enabled.",
            }

        status = "disabled" if self.provider == "none" else "unavailable"
        return {
            "status": status,
            "provider": self.provider,
            "model": self.model_name,
            "message": self.disabled_reason,
        }

    def analyze(
        self,
        extracted_text: str,
        base_analysis: dict[str, Any] | None = None,
        generic_kv: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return self.status()

        text = (extracted_text or "").strip()
        if not text:
            return {
                **self.status(),
                "status": "skipped",
                "message": "No OCR text to send to LLM.",
            }

        prompt = self._build_analysis_prompt(text, base_analysis or {}, generic_kv or {})
        try:
            raw_response = self._call(prompt, require_json=True)
            data = self._parse_json(raw_response)
        except Exception as exc:
            return {
                **self.status(),
                "status": "error",
                "message": f"LLM analysis failed: {exc}",
                "agent_trace": ["LLM request failed or returned invalid JSON."],
            }

        fields = self._normalize_fields(data.get("fields") or self._root_dynamic_fields(data))
        corrected_text = str(data.get("full_corrected_text") or data.get("corrected_text") or "").strip()

        return {
            **self.status(),
            "status": "ok",
            "summary": str(data.get("summary") or "").strip(),
            "full_corrected_text": corrected_text,
            "fields": fields,
            "agent_trace": self._string_list(data.get("agent_trace"))
            or ["LLM corrected OCR text and extracted supplemental fields."],
        }

    def answer_question(
        self,
        question: str,
        extracted_text: str,
        analysis: dict[str, Any] | None = None,
        generic_kv: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled or not question.strip():
            return None

        context = self._compact_context(analysis or {}, generic_kv or {})
        corrected_text = ""
        if analysis:
            llm = analysis.get("llm") or {}
            corrected_text = str(llm.get("full_corrected_text") or analysis.get("full_corrected_text") or "")

        prompt = f"""
You answer questions about an OCR document.
Use only the provided OCR text, corrected text, extracted fields, and generic key-values.
If the answer is not present, say exactly: "Chưa tìm thấy thông tin này trong tài liệu OCR."
Return valid JSON with keys: answer, matched_field, confidence.

Question:
{question}

Extracted fields/context JSON:
{context}

Corrected OCR text:
{self._clip(corrected_text)}

Raw OCR text:
{self._clip(extracted_text)}
"""
        try:
            raw_response = self._call(prompt, require_json=True)
            data = self._parse_json(raw_response)
        except Exception:
            return None

        answer = str(data.get("answer") or "").strip()
        if not answer:
            return None

        return {
            "answer": answer,
            "matched_field": data.get("matched_field") or "llm_answer",
            "source_box_ids": [],
            "confidence": data.get("confidence"),
        }

    def _call(self, prompt: str, require_json: bool) -> str:
        if self.provider != "groq" or self.client is None:
            raise RuntimeError(self.disabled_reason or "LLM is not enabled.")

        response = self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful document parsing assistant. "
                        "Return valid JSON only. Do not invent values."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            model=self.model_name,
            temperature=0.0,
            response_format={"type": "json_object"} if require_json else None,
        )
        return response.choices[0].message.content or "{}"

    def _build_analysis_prompt(
        self,
        extracted_text: str,
        base_analysis: dict[str, Any],
        generic_kv: dict[str, Any],
    ) -> str:
        context = self._compact_context(base_analysis, generic_kv)
        return f"""
You are an OCR post-processing assistant for invoices, contracts, receipts, and forms.
The deterministic system already extracted fields. Your job is supplemental:
1. Correct OCR spelling/diacritic/character mistakes in full_corrected_text.
2. Preserve original line breaks and document order as much as possible.
3. Extract only fields explicitly visible in the OCR text.
4. Do not override reliable numeric fields unless the value is clearly present.

Return valid JSON:
{{
  "summary": "short Vietnamese summary",
  "full_corrected_text": "corrected OCR text preserving line breaks",
  "fields": {{
    "field_name": {{
      "value": "visible value",
      "confidence": 0.0,
      "source": "llm:ocr_correction"
    }}
  }},
  "agent_trace": ["short processing note"]
}}

Deterministic extraction context:
{context}

Raw OCR text:
{self._clip(extracted_text)}
"""

    def _compact_context(self, analysis: dict[str, Any], generic_kv: dict[str, Any]) -> str:
        compact = {
            "document_type": analysis.get("document_type"),
            "summary": analysis.get("summary"),
            "fields": {
                key: value.get("value") if isinstance(value, dict) else value
                for key, value in (analysis.get("fields") or {}).items()
            },
            "generic_key_values": [
                {
                    "label": pair.get("label"),
                    "value": pair.get("display_value") or pair.get("value"),
                    "canonical": pair.get("canonical"),
                }
                for pair in (generic_kv.get("key_values") or [])[:20]
            ],
        }
        return json.dumps(compact, ensure_ascii=False, default=str)

    def _parse_json(self, raw_response: str) -> dict[str, Any]:
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw_response, flags=re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def _normalize_fields(self, fields: dict[str, Any]) -> dict[str, dict[str, Any]]:
        normalized = {}
        for raw_key, raw_value in fields.items():
            key = self._field_key(str(raw_key))
            if not key:
                continue

            if isinstance(raw_value, dict) and "value" in raw_value:
                value = raw_value.get("value")
                confidence = raw_value.get("confidence", 0.62)
                source = raw_value.get("source", "llm:ocr_correction")
            else:
                value = raw_value
                confidence = 0.62
                source = "llm:ocr_correction"

            if self._is_empty_value(value):
                continue

            normalized[key] = {
                "value": value,
                "confidence": self._confidence(confidence),
                "source": source,
            }
        return normalized

    def _root_dynamic_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        reserved = {"summary", "full_corrected_text", "corrected_text", "fields", "agent_trace"}
        return {key: value for key, value in data.items() if key not in reserved}

    def _field_key(self, text: str) -> str:
        cleaned = re.sub(r"[^\w\s-]", "", text.lower(), flags=re.UNICODE)
        cleaned = re.sub(r"[\s-]+", "_", cleaned).strip("_")
        return cleaned[:80]

    def _confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.62
        return round(max(0.0, min(confidence, 1.0)), 2)

    def _is_empty_value(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, dict)):
            return len(value) == 0
        return False

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _clip(self, text: str) -> str:
        text = text or ""
        if len(text) <= self.max_chars:
            return text
        return text[: self.max_chars] + "\n...[truncated]"

    def _load_env_file(self, filename: str) -> None:
        path = Path(filename)
        if not path.exists():
            return

        try:
            from dotenv import load_dotenv

            load_dotenv(path)
            return
        except ImportError:
            pass

        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    def _int_env(self, name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except ValueError:
            return default
