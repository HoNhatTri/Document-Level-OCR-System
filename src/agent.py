from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.generic_kv_extractor import GenericKVExtractor


class DocumentAgent:
    """Rule-based document intelligence layer on top of OCR output.

    This agent intentionally has no external service dependency. It can run
    offline, gives deterministic output, and leaves a clean surface for adding
    an LLM-backed analyzer later.
    """

    LOW_CONFIDENCE_THRESHOLD = 0.55

    DATE_RE = re.compile(
        r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"
    )
    EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.\-]?\d){8,10}(?!\d)")
    AMOUNT_RE = re.compile(
        "(?:(?:VND|VN\\u0110|USD|\\$)\\s*)?-?\\d{1,3}(?:[.,\\s]\\d{3})+(?:[.,]\\d{1,2})?"
        "|(?:-?\\d+(?:[.,]\\d{1,2})?\\s*(?:VND|VN\\u0110|USD|\\$|\\u0111))",
        re.IGNORECASE,
    )

    DOCUMENT_KEYWORDS = {
        "invoice": [
            "hoa don",
            "invoice",
            "vat",
            "ma so thue",
            "mst",
            "tong tien",
            "thanh tien",
            "nguoi ban",
            "nguoi mua",
        ],
        "contract": [
            "hop dong",
            "contract",
            "ben a",
            "ben b",
            "dieu khoan",
            "hieu luc",
            "thoi han",
            "ky ten",
        ],
        "receipt": [
            "bien lai",
            "receipt",
            "phieu thu",
            "da thanh toan",
            "payment",
            "cashier",
        ],
        "warehouse_note": [
            "phieu nhap",
            "phieu xuat",
            "kho",
            "hang hoa",
            "so luong",
            "don vi tinh",
        ],
        "form": [
            "cong hoa",
            "doc lap",
            "don de nghi",
            "to khai",
            "mau so",
            "so cmnd",
            "cccd",
        ],
    }

    TOTAL_KEYWORDS = [
        "tong cong",
        "tong cong tien thanh toan",
        "tong tien thanh toan",
        "tong tien",
        "cong tien hang",
        "thanh toan",
        "amount due",
        "grand total",
        "total",
    ]

    def __init__(self):
        self.kv_extractor = GenericKVExtractor()

    def analyze(
        self,
        extracted_text: str,
        structured_data: dict[str, Any] | None = None,
        bounding_boxes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return a stable AI-style analysis payload for FE and export flows."""

        text = extracted_text or ""
        structured = structured_data or {}
        boxes = bounding_boxes or []
        lines = self._lines_from_structured(structured) or self._lines_from_text(text)
        generic_kv = self.kv_extractor.extract(text, structured)

        document_type, document_type_confidence = self._classify(text)
        fields = self._extract_fields(text, lines, boxes, document_type)
        fields.update(self._fields_from_generic_kv(generic_kv, boxes, fields))
        warnings = self._build_warnings(structured, fields, document_type, text)

        return {
            "document_type": document_type,
            "document_type_confidence": document_type_confidence,
            "summary": self._summarize(document_type, fields, text),
            "fields": fields,
            "warnings": warnings,
            "suggested_tables": self._suggest_tables(structured),
            "generic_kv": generic_kv,
        }

    def answer_question(
        self,
        question: str,
        extracted_text: str,
        analysis: dict[str, Any] | None = None,
        structured_data: dict[str, Any] | None = None,
        bounding_boxes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Small rule-based QA helper for a future FE chat tab."""

        question_text = question or ""
        normalized_question = self._normalize(question_text)
        current_analysis = analysis or self.analyze(
            extracted_text=extracted_text,
            structured_data=structured_data,
            bounding_boxes=bounding_boxes,
        )
        fields = current_analysis.get("fields", {})
        generic_kv = current_analysis.get("generic_kv") or self.kv_extractor.extract(
            extracted_text,
            structured_data or {},
        )
        lines = self._lines_from_structured(structured_data or {}) or self._lines_from_text(extracted_text)

        field_lookup = [
            (["hinh thuc thanh toan", "phuong thuc thanh toan", "payment method", "thanh toan bang gi"], "payment_method"),
            (["tong", "total", "thanh tien", "amount", "bao nhieu tien"], "total_amount"),
            (["ngay", "date", "ngay ky", "ngay lap", "ngay mua"], "primary_date"),
            (["hoa don", "invoice", "so hoa don"], "invoice_number"),
            (["ma so thue", "mst", "tax"], "tax_codes"),
            (["email"], "emails"),
            (["dien thoai", "phone", "sdt"], "phone_numbers"),
            (["ben a", "party a"], "party_a"),
            (["ben b", "party b"], "party_b"),
            (["nguoi ban", "ben ban", "don vi ban", "seller"], "seller"),
            (["nguoi mua", "ben mua", "don vi mua", "buyer", "ai la ben mua"], "buyer"),
            (["mau so"], "invoice_form"),
            (["ky hieu"], "invoice_symbol"),
            (["so tien bang chu", "bang chu"], "amount_in_words"),
        ]

        for keywords, field_name in field_lookup:
            if any(keyword in normalized_question for keyword in keywords):
                field = fields.get(field_name)
                if field:
                    return {
                        "answer": self._humanize_field(field_name, field),
                        "matched_field": field_name,
                        "source_box_ids": field.get("source_box_ids", []),
                    }
                fallback_answer = self._answer_field_from_lines(field_name, lines)
                if fallback_answer:
                    return fallback_answer
                generic_answer = self._answer_field_from_generic_kv(field_name, generic_kv)
                if generic_answer:
                    return generic_answer

        if any(keyword in normalized_question for keyword in ["tom tat", "tom luoc", "summary", "noi dung chinh", "noi dung", "noi ve"]):
            return {
                "answer": current_analysis.get("summary", "Chưa có tóm tắt cho tài liệu này."),
                "matched_field": "summary",
                "source_box_ids": [],
            }

        generic_answer = self.kv_extractor.answer_from_question(question_text, generic_kv)
        if generic_answer:
            return generic_answer

        matched_lines = self._find_relevant_lines(question_text, extracted_text)
        if matched_lines:
            return {
                "answer": "\n".join(matched_lines[:5]),
                "matched_field": "text_search",
                "source_box_ids": [],
            }

        return {
            "answer": "Chưa tìm thấy câu trả lời rõ ràng trong tài liệu OCR.",
            "matched_field": None,
            "source_box_ids": [],
        }

    def _classify(self, text: str) -> tuple[str, float]:
        normalized = self._normalize(text)
        scores: dict[str, int] = {}

        for document_type, keywords in self.DOCUMENT_KEYWORDS.items():
            score = sum(normalized.count(keyword) for keyword in keywords)
            if score:
                scores[document_type] = score

        if not scores:
            return "general_document", 0.35

        best_type, best_score = max(scores.items(), key=lambda item: item[1])
        confidence = min(0.95, 0.5 + (best_score / (best_score + 6)) * 0.45)
        return best_type, round(confidence, 2)

    def _extract_fields(
        self,
        text: str,
        lines: list[dict[str, Any]],
        boxes: list[dict[str, Any]],
        document_type: str,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {}

        dates = self._unique_matches(self.DATE_RE.findall(text))
        if dates:
            fields["primary_date"] = self._field(dates[0], 0.76, "regex:date", boxes, dates[0])
            fields["dates"] = self._field(dates, 0.7, "regex:date", boxes, " ".join(dates[:3]))

        emails = self._unique_matches(self.EMAIL_RE.findall(text))
        if emails:
            fields["emails"] = self._field(emails, 0.88, "regex:email", boxes, " ".join(emails))

        phones = self._extract_phone_numbers(text)
        if phones:
            fields["phone_numbers"] = self._field(phones, 0.75, "regex:phone", boxes, " ".join(phones))

        tax_codes = self._extract_tax_codes(lines)
        if tax_codes:
            fields["tax_codes"] = self._field(tax_codes, 0.82, "regex:tax_code", boxes, " ".join(tax_codes))

        total_amount = self._extract_total_amount(lines, text)
        if total_amount:
            fields["total_amount"] = self._field(
                total_amount["value"],
                total_amount["confidence"],
                total_amount["source"],
                boxes,
                total_amount["raw"],
                {"raw": total_amount["raw"], "currency": total_amount["currency"]},
            )

        invoice_number = self._extract_invoice_number(lines)
        if invoice_number:
            fields["invoice_number"] = self._field(
                invoice_number["value"],
                invoice_number["confidence"],
                invoice_number["source"],
                boxes,
                invoice_number["source_text"],
            )

        parties = self._extract_parties(lines, document_type)
        fields.update(parties)
        fields.update(self._extract_vietnamese_invoice_fields(lines, boxes, fields))

        return fields

    def _extract_phone_numbers(self, text: str) -> list[str]:
        phones = []
        for match in self.PHONE_RE.findall(text):
            digits = re.sub(r"\D", "", match)
            if len(digits) >= 9:
                phones.append(match.strip())
        return self._unique_matches(phones)

    def _extract_tax_codes(self, lines: list[dict[str, Any]]) -> list[str]:
        tax_codes = []
        for line in lines:
            raw = line["text"]
            normalized = self._normalize(raw)
            if not any(keyword in normalized for keyword in ["mst", "ma so thue", "tax code", "tax id"]):
                continue
            for match in re.findall(r"\b\d{10}(?:[-\s]?\d{3})?\b", raw):
                tax_codes.append(match.strip())
        return self._unique_matches(tax_codes)

    def _extract_total_amount(self, lines: list[dict[str, Any]], text: str) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []

        for line in lines:
            raw_line = line["text"]
            normalized_line = self._normalize(raw_line)
            keyword_score = sum(keyword in normalized_line for keyword in self.TOTAL_KEYWORDS)
            if not keyword_score:
                continue
            for amount_text in self.AMOUNT_RE.findall(raw_line):
                parsed = self._parse_amount(amount_text)
                if parsed is None:
                    continue
                candidates.append(
                    {
                        "value": parsed,
                        "raw": amount_text.strip(),
                        "currency": self._detect_currency(amount_text),
                        "confidence": min(0.92, 0.72 + keyword_score * 0.06),
                        "source": "line:total_keyword",
                    }
                )

        if candidates:
            return max(candidates, key=lambda item: item["value"])

        all_amounts = []
        for amount_text in self.AMOUNT_RE.findall(text):
            parsed = self._parse_amount(amount_text)
            if parsed is not None:
                all_amounts.append(
                    {
                        "value": parsed,
                        "raw": amount_text.strip(),
                        "currency": self._detect_currency(amount_text),
                        "confidence": 0.55,
                        "source": "regex:largest_amount",
                    }
                )
        return max(all_amounts, key=lambda item: item["value"]) if all_amounts else None

    def _extract_invoice_number(self, lines: list[dict[str, Any]]) -> dict[str, Any] | None:
        patterns = [
            re.compile(r"(?:so hoa don|hoa don so|so hd|so|no|number|invoice)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\-/.]{2,})", re.IGNORECASE),
            re.compile(r"(?:hoa don|invoice).*?([A-Z0-9]{2,}[-/.]?\d{2,})", re.IGNORECASE),
        ]

        for line in lines:
            normalized = self._normalize(line["text"])
            if "ma so thue" in normalized or "mst" in normalized:
                continue
            if not any(keyword in normalized for keyword in ["hoa don", "invoice", "so", "no", "so hd"]):
                continue
            for pattern in patterns:
                match = pattern.search(line["text"])
                if match:
                    return {
                        "value": match.group(1).strip(),
                        "confidence": 0.72,
                        "source": "regex:invoice_number",
                        "source_text": line["text"],
                    }
        return None

    def _extract_parties(self, lines: list[dict[str, Any]], document_type: str) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        labels = {
            "party_a": ["ben a", "party a"],
            "party_b": ["ben b", "party b"],
            "seller": ["nguoi ban", "seller", "vendor", "from", "don vi ban", "don vi ban hang", "ben ban"],
            "buyer": [
                "nguoi mua",
                "buyer",
                "customer",
                "client",
                "bill to",
                "billed to",
                "billing to",
                "don vi mua",
                "nguoi mua hang",
                "khach hang",
                "ben mua",
            ],
        }

        for field_name, keywords in labels.items():
            match = self._extract_first_labeled_value(lines, keywords)
            if match:
                fields[field_name] = {
                    "value": match["value"],
                    "confidence": 0.68 if document_type in ["contract", "invoice"] else 0.58,
                    "source": f"line:{field_name}",
                    "source_box_ids": [],
                }

        return fields

    def _answer_field_from_lines(
        self,
        field_name: str,
        lines: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        label_map = {
            "buyer": [
                "ho ten nguoi mua hang",
                "nguoi mua hang",
                "ten nguoi mua",
                "nguoi mua",
                "don vi mua",
                "ten don vi mua",
                "khach hang",
                "bill to",
                "billed to",
                "billing to",
                "customer",
                "client",
                "ben mua",
            ],
            "seller": [
                "don vi ban hang",
                "ten nguoi ban",
                "nguoi ban",
                "ten don vi ban",
                "ben ban",
                "seller",
                "vendor",
                "from",
            ],
            "payment_method": ["hinh thuc thanh toan", "phuong thuc thanh toan", "payment method"],
            "invoice_number": ["so hoa don", "hoa don so", "so hd"],
            "invoice_form": ["mau so"],
            "invoice_symbol": ["ky hieu"],
            "amount_in_words": ["so tien viet bang chu", "bang chu"],
        }

        labels = label_map.get(field_name)
        if not labels:
            return None

        match = self._extract_first_labeled_value(lines, labels)
        if not match:
            return None

        return {
            "answer": match["value"],
            "matched_field": field_name,
            "source_box_ids": [],
        }

    def _answer_field_from_generic_kv(
        self,
        field_name: str,
        generic_kv: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        pair = self.kv_extractor.find_by_field(field_name, generic_kv)
        if not pair:
            return None

        return {
            "answer": pair.get("display_value") or pair.get("value", ""),
            "matched_field": field_name,
            "source_box_ids": pair.get("source_box_ids", []),
        }

    def _fields_from_generic_kv(
        self,
        generic_kv: dict[str, Any],
        boxes: list[dict[str, Any]],
        existing_fields: dict[str, Any],
    ) -> dict[str, Any]:
        fields = {}
        canonical_to_field = {
            "buyer": "buyer",
            "seller": "seller",
            "shipping_address": "shipping_address",
            "billing_address": "billing_address",
            "invoice_number": "invoice_number",
            "payment_method": "payment_method",
            "invoice_form": "invoice_form",
            "invoice_symbol": "invoice_symbol",
        }

        for pair in generic_kv.get("key_values", []):
            canonical = pair.get("canonical")
            field_name = canonical_to_field.get(canonical)
            if not field_name or field_name in existing_fields or field_name in fields:
                continue

            value = pair.get("display_value") or pair.get("value", "")
            if not value:
                continue

            fields[field_name] = self._field(
                value,
                pair.get("confidence", 0.6),
                f"generic_kv:{pair.get('source', 'unknown')}",
                boxes,
                f"{pair.get('label', '')} {value}",
            )

            full_value = pair.get("value", "")
            value_lines = [line.strip() for line in full_value.splitlines() if line.strip()]
            if field_name == "buyer" and len(value_lines) > 1 and "buyer_address" not in existing_fields:
                fields["buyer_address"] = self._field(
                    "\n".join(value_lines[1:]),
                    pair.get("confidence", 0.58),
                    f"generic_kv:{pair.get('source', 'unknown')}",
                    boxes,
                    full_value,
                )
            if field_name == "seller" and len(value_lines) > 1 and "seller_address" not in existing_fields:
                fields["seller_address"] = self._field(
                    "\n".join(value_lines[1:]),
                    pair.get("confidence", 0.58),
                    f"generic_kv:{pair.get('source', 'unknown')}",
                    boxes,
                    full_value,
                )

        return fields

    def _extract_vietnamese_invoice_fields(
        self,
        lines: list[dict[str, Any]],
        boxes: list[dict[str, Any]],
        existing_fields: dict[str, Any],
    ) -> dict[str, Any]:
        field_specs = {
            "invoice_form": {
                "labels": ["mau so", "form"],
                "confidence": 0.74,
                "source": "line:mau_so",
            },
            "invoice_symbol": {
                "labels": ["ky hieu", "serial"],
                "confidence": 0.74,
                "source": "line:ky_hieu",
            },
            "payment_method": {
                "labels": ["hinh thuc thanh toan", "payment method"],
                "confidence": 0.68,
                "source": "line:hinh_thuc_thanh_toan",
            },
            "amount_in_words": {
                "labels": ["so tien viet bang chu", "bang chu", "amount in words"],
                "confidence": 0.66,
                "source": "line:so_tien_bang_chu",
            },
            "seller_address": {
                "labels": ["dia chi nguoi ban", "dia chi ben ban"],
                "confidence": 0.62,
                "source": "line:dia_chi_nguoi_ban",
            },
            "buyer_address": {
                "labels": ["dia chi nguoi mua", "dia chi ben mua"],
                "confidence": 0.62,
                "source": "line:dia_chi_nguoi_mua",
            },
        }

        fields: dict[str, Any] = {}
        for field_name, spec in field_specs.items():
            if field_name in existing_fields:
                continue
            match = self._extract_first_labeled_value(lines, spec["labels"])
            if match:
                fields[field_name] = self._field(
                    match["value"],
                    spec["confidence"],
                    spec["source"],
                    boxes,
                    match["source_text"],
                )

        if "invoice_number" not in existing_fields:
            match = self._extract_first_labeled_value(lines, ["so hoa don", "hoa don so", "so hd"])
            if match:
                fields["invoice_number"] = self._field(
                    match["value"],
                    0.74,
                    "line:so_hoa_don",
                    boxes,
                    match["source_text"],
                )

        if "seller" not in existing_fields:
            match = self._extract_first_labeled_value(
                lines,
                ["don vi ban hang", "ten nguoi ban", "nguoi ban", "ben ban", "seller", "vendor", "from"],
            )
            if match:
                fields["seller"] = self._field(
                    match["value"],
                    0.7,
                    "line:nguoi_ban",
                    boxes,
                    match["source_text"],
                )

        if "buyer" not in existing_fields:
            match = self._extract_first_labeled_value(
                lines,
                [
                    "ho ten nguoi mua hang",
                    "nguoi mua hang",
                    "ten nguoi mua",
                    "nguoi mua",
                    "ben mua",
                    "bill to",
                    "billed to",
                    "billing to",
                    "customer",
                    "client",
                ],
            )
            if match:
                fields["buyer"] = self._field(
                    match["value"],
                    0.7,
                    "line:nguoi_mua",
                    boxes,
                    match["source_text"],
                )

        return fields

    def _extract_first_labeled_value(
        self,
        lines: list[dict[str, Any]],
        labels: list[str],
    ) -> dict[str, str] | None:
        for index, line in enumerate(lines):
            normalized = self._normalize(line["text"])
            if not any(label in normalized for label in labels):
                continue
            value = self._value_after_separator(line["text"])
            if not value or self._normalize(value) == normalized:
                value = self._remove_label_prefix(line["text"], labels)
            if not value:
                value = self._next_value_line(lines, index)
            if value:
                return {"value": value, "source_text": line["text"]}
        return None

    def _next_value_line(self, lines: list[dict[str, Any]], current_index: int) -> str:
        for next_line in lines[current_index + 1 : current_index + 4]:
            text = next_line.get("text", "").strip()
            if not text:
                continue
            if self._looks_like_label_line(text):
                break
            return text
        return ""

    def _looks_like_label_line(self, text: str) -> bool:
        normalized = self._normalize(text)
        labels = [
            "mau so",
            "ky hieu",
            "so hoa don",
            "ngay",
            "ma so thue",
            "mst",
            "nguoi mua",
            "nguoi ban",
            "don vi mua",
            "don vi ban",
            "dia chi",
            "hinh thuc thanh toan",
            "tong cong",
            "tong tien",
            "cong tien hang",
        ]
        return any(label in normalized for label in labels)

    def _remove_label_prefix(self, text: str, labels: list[str]) -> str:
        normalized = self._normalize(text)
        for label in sorted(labels, key=len, reverse=True):
            index = normalized.find(label)
            if index < 0:
                continue
            return text[index + len(label):].strip(" :-–")
        return ""

    def _build_warnings(
        self,
        structured_data: dict[str, Any],
        fields: dict[str, Any],
        document_type: str,
        text: str,
    ) -> list[dict[str, Any]]:
        warnings = []

        if not text.strip():
            warnings.append(
                {
                    "type": "empty_text",
                    "message": "OCR không trả về nội dung văn bản.",
                    "severity": "high",
                    "source_box_ids": [],
                }
            )

        low_confidence_words = self._low_confidence_words(structured_data)
        for item in low_confidence_words[:8]:
            warnings.append(
                {
                    "type": "low_confidence_word",
                    "message": f"Từ '{item['value']}' có độ tin cậy thấp ({item['confidence']:.2f}).",
                    "severity": "medium",
                    "source_box_ids": [],
                }
            )

        if document_type in ["invoice", "receipt"] and "total_amount" not in fields:
            warnings.append(
                {
                    "type": "missing_total_amount",
                    "message": "Chưa tìm thấy tổng tiền rõ ràng trong tài liệu.",
                    "severity": "medium",
                    "source_box_ids": [],
                }
            )

        if document_type == "invoice" and "tax_codes" not in fields:
            warnings.append(
                {
                    "type": "missing_tax_code",
                    "message": "Chưa tìm thấy mã số thuế/MST.",
                    "severity": "low",
                    "source_box_ids": [],
                }
            )

        return warnings

    def _low_confidence_words(self, structured_data: dict[str, Any]) -> list[dict[str, Any]]:
        words = []
        for page in structured_data.get("pages", []):
            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    for word in line.get("words", []):
                        confidence = word.get("confidence")
                        if confidence is None or confidence >= self.LOW_CONFIDENCE_THRESHOLD:
                            continue
                        words.append({"value": word.get("value", ""), "confidence": float(confidence)})
        return words

    def _suggest_tables(self, structured_data: dict[str, Any]) -> list[dict[str, Any]]:
        table_like_pages = []
        for page_index, page in enumerate(structured_data.get("pages", []), start=1):
            line_count = sum(
                len(block.get("lines", []))
                for block in page.get("blocks", [])
            )
            if line_count >= 12:
                table_like_pages.append(
                    {
                        "page": page_index,
                        "type": "line_grid_candidate",
                        "message": "Trang co nhieu dong; co the can module table extraction rieng.",
                    }
                )
        return table_like_pages

    def _summarize(self, document_type: str, fields: dict[str, Any], text: str) -> str:
        labels = {
            "invoice": "Tài liệu có dấu hiệu là hóa đơn",
            "contract": "Tài liệu có dấu hiệu là hợp đồng",
            "receipt": "Tài liệu có dấu hiệu là biên lai/phiếu thu",
            "warehouse_note": "Tài liệu có dấu hiệu là phiếu kho",
            "form": "Tài liệu có dấu hiệu là biểu mẫu hành chính",
            "general_document": "Tài liệu văn bản tổng quát",
        }
        parts = [labels.get(document_type, "Tài liệu văn bản")]

        if "primary_date" in fields:
            parts.append(f"ngày {fields['primary_date']['value']}")
        if "total_amount" in fields:
            total = fields["total_amount"]
            currency = total.get("currency") or ""
            parts.append(f"tổng tiền {total['value']} {currency}".strip())
        if "invoice_number" in fields:
            parts.append(f"số {fields['invoice_number']['value']}")

        if len(parts) > 1:
            return ", ".join(parts) + "."

        first_lines = [line.strip() for line in text.splitlines() if line.strip()]
        preview = " ".join(first_lines[:2])
        return preview[:220] if preview else parts[0] + "."

    def _lines_from_structured(self, structured_data: dict[str, Any]) -> list[dict[str, Any]]:
        lines = []
        for page_index, page in enumerate(structured_data.get("pages", []), start=1):
            for block_index, block in enumerate(page.get("blocks", []), start=1):
                for line_index, line in enumerate(block.get("lines", []), start=1):
                    text = " ".join(
                        word.get("value", "")
                        for word in line.get("words", [])
                        if word.get("value")
                    ).strip()
                    if text:
                        lines.append(
                            {
                                "text": text,
                                "page": page_index,
                                "block": block_index,
                                "line": line_index,
                                "geometry": line.get("geometry"),
                            }
                        )
        return lines

    def _lines_from_text(self, text: str) -> list[dict[str, Any]]:
        return [
            {"text": line.strip(), "page": 1, "block": 1, "line": index + 1, "geometry": None}
            for index, line in enumerate(text.splitlines())
            if line.strip()
        ]

    def _field(
        self,
        value: Any,
        confidence: float,
        source: str,
        boxes: list[dict[str, Any]],
        lookup_text: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        field = {
            "value": value,
            "confidence": round(confidence, 2),
            "source": source,
            "source_box_ids": self._box_ids_for_text(boxes, lookup_text),
        }
        if extra:
            field.update(extra)
        return field

    def _box_ids_for_text(self, boxes: list[dict[str, Any]], text: str) -> list[str]:
        normalized_lookup = self._normalize(text)
        if not normalized_lookup:
            return []

        ids = []
        for box in boxes:
            label = self._normalize(str(box.get("label", "")))
            if label and (normalized_lookup in label or label in normalized_lookup):
                ids.append(str(box.get("id")))
        return ids[:5]

    def _find_relevant_lines(self, question: str, text: str) -> list[str]:
        keywords = [
            token
            for token in re.findall(r"[A-Za-z0-9_]+", self._normalize(question))
            if len(token) >= 4
        ]
        if not keywords:
            return []

        matched = []
        for line in text.splitlines():
            normalized_line = self._normalize(line)
            if any(keyword in normalized_line for keyword in keywords):
                matched.append(line.strip())
        return matched

    def _humanize_field(self, field_name: str, field: dict[str, Any]) -> str:
        value = field.get("value")
        if isinstance(value, list):
            display = ", ".join(str(item) for item in value)
        else:
            display = str(value)

        if field_name == "total_amount" and field.get("currency"):
            display = f"{display} {field['currency']}"

        confidence = field.get("confidence")
        if confidence is None:
            return display
        return f"{display} (độ tin cậy {round(float(confidence) * 100)}%)"

    def _value_after_separator(self, text: str) -> str:
        for separator in [":", "-", "\u2013"]:
            if separator in text:
                return text.split(separator, 1)[1].strip()
        return text.strip()

    def _unique_matches(self, values: list[str]) -> list[str]:
        seen = set()
        result = []
        for value in values:
            cleaned = value.strip()
            key = self._normalize(cleaned)
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result

    def _parse_amount(self, raw: str) -> float | int | None:
        cleaned = re.sub(r"[^\d,.\-]", "", raw).strip()
        if not cleaned or cleaned in {"-", ".", ","}:
            return None

        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            groups = cleaned.split(",")
            cleaned = cleaned.replace(",", "") if len(groups[-1]) == 3 else cleaned.replace(",", ".")
        elif "." in cleaned:
            groups = cleaned.split(".")
            if len(groups) > 2 or len(groups[-1]) == 3:
                cleaned = cleaned.replace(".", "")

        try:
            amount = float(cleaned)
        except ValueError:
            return None

        if amount.is_integer():
            return int(amount)
        return amount

    def _detect_currency(self, raw: str) -> str | None:
        normalized = self._normalize(raw)
        if "usd" in normalized or "$" in raw:
            return "USD"
        if "vnd" in normalized or "vn\u0111" in raw.lower() or "\u0111" in raw.lower():
            return "VND"
        return None

    def _normalize(self, text: str) -> str:
        decomposed = unicodedata.normalize("NFD", text.lower())
        no_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
        return no_marks.replace("\u0111", "d")
