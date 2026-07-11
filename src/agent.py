from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.generic_kv_extractor import GenericKVExtractor
from src.layoutxlm_extractor import OptionalLayoutXLMExtractor
from src.llm_agent import OptionalLLMAgent


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

    def __init__(
        self,
        llm_agent: OptionalLLMAgent | None = None,
        layoutxlm_extractor: OptionalLayoutXLMExtractor | None = None,
    ):
        self.kv_extractor = GenericKVExtractor()
        self.llm_agent = llm_agent if llm_agent is not None else OptionalLLMAgent()
        self.layoutxlm_extractor = (
            layoutxlm_extractor
            if layoutxlm_extractor is not None
            else OptionalLayoutXLMExtractor()
        )

    def analyze(
        self,
        extracted_text: str,
        structured_data: dict[str, Any] | None = None,
        bounding_boxes: list[dict[str, Any]] | None = None,
        page_images: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Return a stable AI-style analysis payload for FE and export flows."""

        text = extracted_text or ""
        structured = structured_data or {}
        boxes = bounding_boxes or []
        lines = self._lines_from_structured(structured) or self._lines_from_text(text)
        generic_kv = self.kv_extractor.extract(text, structured)

        document_type, document_type_confidence = self._classify(text)
        fields = self._extract_fields(text, lines, boxes, document_type)
        fields.update(self._fields_from_generic_kv(generic_kv, boxes, fields, document_type))
        layoutxlm_analysis = self.layoutxlm_extractor.extract(
            page_images=page_images,
            structured_data=structured,
            document_type=document_type,
        )
        layoutxlm_fields = (
            layoutxlm_analysis.get("fields", {})
            if isinstance(layoutxlm_analysis, dict)
            else {}
        )
        layoutxlm_fields, rejected_layoutxlm_fields = self._filter_layoutxlm_fields(
            layoutxlm_fields,
            document_type,
        )
        if isinstance(layoutxlm_analysis, dict):
            layoutxlm_analysis = dict(layoutxlm_analysis)
            if rejected_layoutxlm_fields:
                layoutxlm_analysis["raw_fields"] = layoutxlm_analysis.get("fields", {})
                layoutxlm_analysis["rejected_fields"] = rejected_layoutxlm_fields
            layoutxlm_analysis["fields"] = layoutxlm_fields
        fields.update(
            self._fields_from_layoutxlm(
                layoutxlm_fields,
                boxes,
                fields,
                document_type,
            )
        )
        preliminary_analysis = {
            "document_type": document_type,
            "document_type_confidence": document_type_confidence,
            "summary": self._summarize(document_type, fields, text),
            "fields": fields,
            "generic_kv": generic_kv,
            "layoutxlm_fields": layoutxlm_fields,
        }
        llm_analysis = self.llm_agent.analyze(
            extracted_text=text,
            base_analysis=preliminary_analysis,
            generic_kv=generic_kv,
        )
        llm_fields = llm_analysis.get("fields", {}) if isinstance(llm_analysis, dict) else {}
        fields.update(self._fields_from_llm(llm_fields, boxes, fields, document_type))
        warnings = self._build_warnings(structured, fields, document_type, text)
        summary = self._summarize(document_type, fields, text)
        if llm_analysis.get("status") == "ok" and llm_analysis.get("summary"):
            summary = llm_analysis["summary"]

        return {
            "document_type": document_type,
            "document_type_confidence": document_type_confidence,
            "summary": summary,
            "fields": fields,
            "warnings": warnings,
            "suggested_tables": self._suggest_tables(structured),
            "generic_kv": generic_kv,
            "layoutxlm": layoutxlm_analysis,
            "layoutxlm_fields": layoutxlm_fields,
            "llm": llm_analysis,
            "llm_fields": llm_fields,
            "full_corrected_text": llm_analysis.get("full_corrected_text", ""),
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
                direct_generic_answer = self.kv_extractor.answer_from_question(question_text, generic_kv)
                if direct_generic_answer and self._generic_answer_matches_field(direct_generic_answer, field_name):
                    return direct_generic_answer

                generic_answer = self._answer_field_from_generic_kv(field_name, generic_kv)
                if generic_answer:
                    return generic_answer
                fallback_answer = self._answer_field_from_lines(field_name, lines)
                if fallback_answer:
                    return fallback_answer
                llm_field_answer = self._answer_field_from_llm_fields(
                    field_name,
                    current_analysis,
                    fields.get(field_name),
                )
                if llm_field_answer:
                    return llm_field_answer
                field = fields.get(field_name)
                if field:
                    return {
                        "answer": self._humanize_field(field_name, field),
                        "matched_field": field_name,
                        "source_box_ids": field.get("source_box_ids", []),
                    }

        if any(keyword in normalized_question for keyword in ["tom tat", "tom luoc", "summary", "noi dung chinh", "noi dung", "noi ve"]):
            return {
                "answer": current_analysis.get("summary", "Chưa có tóm tắt cho tài liệu này."),
                "matched_field": "summary",
                "source_box_ids": [],
            }

        generic_answer = self.kv_extractor.answer_from_question(question_text, generic_kv)
        if generic_answer:
            return generic_answer

        llm_answer = self.llm_agent.answer_question(
            question=question_text,
            extracted_text=extracted_text,
            analysis=current_analysis,
            generic_kv=generic_kv,
        )
        if llm_answer:
            return llm_answer

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
        invoice_score = self._score_invoice(normalized)
        if invoice_score >= 4:
            confidence = min(0.94, 0.58 + invoice_score * 0.055)
            return "invoice", round(confidence, 2)

        scores: dict[str, int] = {}
        for document_type, keywords in self.DOCUMENT_KEYWORDS.items():
            if document_type == "invoice":
                continue
            score = sum(self._contains_phrase(normalized, keyword) for keyword in keywords)
            if score:
                scores[document_type] = score

        if not scores:
            return "general_document", 0.35

        best_type, best_score = max(scores.items(), key=lambda item: item[1])
        confidence = min(0.95, 0.5 + (best_score / (best_score + 6)) * 0.45)
        return best_type, round(confidence, 2)

    def _score_invoice(self, normalized: str) -> int:
        strong_patterns = [
            r"\binvoice\s*#(?=\s|$)",
            r"\binvoice\s*(?:no|number|date)\b",
            r"\b(?:bill|billed|billing)\s+to\b",
            r"\bship\s+to\b",
            r"\bamount\s+due\b",
            r"\bbalance\s+due\b",
            r"\bsub\s*total\b",
            r"\btax\s+rate\b",
            r"\btax\s+code\b",
            r"\bhoa don\s*(?:so)?\b",
            r"\bso hoa don\b",
            r"\bmau so\b",
            r"\bky hieu\b",
            r"\bma so thue\b",
            r"\bmst\b",
            r"\bdon vi ban hang\b",
            r"\bnguoi mua hang\b",
            r"\btong cong tien thanh toan\b",
        ]
        medium_patterns = [
            r"\binvoice\b",
            r"\bvat\b",
            r"\bsubtotal\b",
            r"\btotal\b",
            r"\bamount\b",
            r"\bpayment method\b",
            r"\bseller\b",
            r"\bbuyer\b",
            r"\bnguoi ban\b",
            r"\bnguoi mua\b",
            r"\btong tien\b",
            r"\bthanh tien\b",
        ]
        weak_reference_patterns = [
            r"\binvoices\b",
            r"\breceipts\b",
            r"\bbank statements\b",
            r"\bpassport documents\b",
            r"\bdata records\b",
        ]

        strong_score = sum(2 for pattern in strong_patterns if re.search(pattern, normalized))
        medium_score = sum(1 for pattern in medium_patterns if re.search(pattern, normalized))
        weak_reference_score = sum(1 for pattern in weak_reference_patterns if re.search(pattern, normalized))

        score = strong_score + medium_score
        if strong_score == 0 and score <= 2:
            return 0
        if weak_reference_score >= 2 and strong_score == 0:
            return 0
        return score

    def _contains_phrase(self, normalized: str, phrase: str) -> bool:
        escaped = re.escape(phrase)
        return bool(re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", normalized))

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

        if self._needs_invoice_fields(document_type):
            tax_codes = self._extract_tax_codes(lines)
            if tax_codes:
                fields["tax_codes"] = self._field(tax_codes, 0.82, "regex:tax_code", boxes, " ".join(tax_codes))

            invoice_number = self._extract_invoice_number(lines)
            if invoice_number:
                fields["invoice_number"] = self._field(
                    invoice_number["value"],
                    invoice_number["confidence"],
                    invoice_number["source"],
                    boxes,
                    invoice_number["source_text"],
                )

        if self._needs_financial_fields(document_type):
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

        parties = self._extract_parties(lines, document_type)
        fields.update(parties)
        if self._needs_invoice_fields(document_type):
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

    def _generic_answer_matches_field(self, answer: dict[str, Any], field_name: str) -> bool:
        matched_field = answer.get("matched_field")
        if matched_field == field_name:
            return True
        if matched_field != "generic_kv":
            return False

        # Generic answers without a canonical field are accepted only for
        # fields where the question text directly matched a detected label.
        return field_name in {
            "total_amount",
            "primary_date",
            "tax_codes",
            "emails",
            "phone_numbers",
            "amount_in_words",
        }

    def _fields_from_generic_kv(
        self,
        generic_kv: dict[str, Any],
        boxes: list[dict[str, Any]],
        existing_fields: dict[str, Any],
        document_type: str,
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
            if not field_name:
                continue
            if not self._field_allowed_for_document(field_name, document_type):
                continue

            value = pair.get("display_value") or pair.get("value", "")
            if not value:
                continue

            existing_field = fields.get(field_name) or existing_fields.get(field_name)
            if existing_field and not self._should_replace_with_generic_field(field_name, existing_field, pair):
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

    def _fields_from_layoutxlm(
        self,
        layoutxlm_fields: dict[str, Any],
        boxes: list[dict[str, Any]],
        existing_fields: dict[str, Any],
        document_type: str,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if not isinstance(layoutxlm_fields, dict):
            return fields

        for field_name, candidate in layoutxlm_fields.items():
            if not isinstance(candidate, dict):
                continue
            if not self._field_allowed_for_document(field_name, document_type):
                continue

            raw_value = candidate.get("value")
            if self._is_empty_value(raw_value):
                continue

            value = raw_value
            extra: dict[str, Any] = {
                "layoutxlm_label": candidate.get("source", "").split(":")[-1],
            }
            if field_name == "total_amount":
                parsed_amount = self._parse_amount(str(raw_value))
                if parsed_amount is None:
                    continue
                value = parsed_amount
                extra.update(
                    {
                        "raw": str(raw_value),
                        "currency": self._detect_currency(str(raw_value)),
                    }
                )

            confidence = self._safe_confidence(
                candidate.get("confidence"),
                default=0.55,
            )
            existing = fields.get(field_name) or existing_fields.get(field_name)
            if existing and not self._should_replace_with_layoutxlm(
                existing,
                confidence,
            ):
                continue

            fields[field_name] = self._field(
                value,
                confidence,
                str(candidate.get("source") or "layoutxlm:token_classification"),
                boxes,
                str(raw_value),
                extra,
            )

        return fields

    def _filter_layoutxlm_fields(
        self,
        layoutxlm_fields: dict[str, Any],
        document_type: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        valid_fields: dict[str, Any] = {}
        rejected_fields: dict[str, Any] = {}
        if not isinstance(layoutxlm_fields, dict):
            return valid_fields, rejected_fields

        for field_name, candidate in layoutxlm_fields.items():
            if not isinstance(candidate, dict):
                continue
            if not self._field_allowed_for_document(field_name, document_type):
                continue

            reason = self._layoutxlm_rejection_reason(field_name, candidate.get("value"))
            if reason:
                rejected_candidate = dict(candidate)
                rejected_candidate["rejection_reason"] = reason
                rejected_fields[field_name] = rejected_candidate
                continue

            valid_fields[field_name] = candidate

        return valid_fields, rejected_fields

    def _layoutxlm_rejection_reason(self, field_name: str, value: Any) -> str:
        if self._is_empty_value(value):
            return "empty_value"

        text = str(value).strip()
        normalized = self._normalize(text)
        if self._is_layoutxlm_label_like_value(normalized):
            return "label_like_value"

        if field_name == "primary_date":
            if not self._looks_like_date_value(text):
                return "invalid_date_format"
            return ""

        if field_name == "total_amount":
            parsed = self._parse_amount(text)
            if parsed is None or float(parsed) <= 0:
                return "invalid_amount"
            return ""

        if field_name == "invoice_number":
            if len(text) < 2 or not any(char.isalnum() for char in text):
                return "invalid_invoice_number"
            return ""

        if field_name in {
            "seller",
            "buyer",
            "seller_address",
            "buyer_address",
            "shipping_address",
            "billing_address",
        }:
            alpha_count = sum(char.isalpha() for char in text)
            if len(text) < 3 or alpha_count < 2:
                return "too_short_or_numeric"
            return ""

        return ""

    def _is_layoutxlm_label_like_value(self, normalized: str) -> bool:
        label_values = {
            "date",
            "invoice",
            "invoice date",
            "due date",
            "invoice due date",
            "invoice #",
            "invoice no",
            "invoice number",
            "bill to",
            "ship to",
            "seller",
            "buyer",
            "address",
            "total",
            "subtotal",
            "sub total",
            "amount",
            "amount due",
            "balance due",
            "tax",
            "rate",
            "qty",
        }
        return normalized in label_values

    def _looks_like_date_value(self, text: str) -> bool:
        if self.DATE_RE.search(text):
            return True

        normalized = self._normalize(text)
        months = (
            "jan|january|feb|february|mar|march|apr|april|may|jun|june|"
            "jul|july|aug|august|sep|sept|september|oct|october|"
            "nov|november|dec|december"
        )
        return bool(
            re.search(rf"\b\d{{1,2}}\s+(?:{months})\s+\d{{2,4}}\b", normalized)
            or re.search(rf"\b(?:{months})\s+\d{{1,2}},?\s+\d{{2,4}}\b", normalized)
            or re.search(r"\b\d{1,2}\s+thang\s+\d{1,2}\s+\d{2,4}\b", normalized)
        )

    def _fields_from_llm(
        self,
        llm_fields: dict[str, Any],
        boxes: list[dict[str, Any]],
        existing_fields: dict[str, Any],
        document_type: str,
    ) -> dict[str, Any]:
        fields = {}
        if not isinstance(llm_fields, dict):
            return fields

        for field_name, field in llm_fields.items():
            normalized_name = self._normalize_dynamic_field_name(str(field_name))
            if not normalized_name or normalized_name in fields:
                continue
            if not self._field_allowed_for_document(normalized_name, document_type):
                continue

            if isinstance(field, dict) and "value" in field:
                value = field.get("value")
                confidence = field.get("confidence", 0.62)
                source = field.get("source", "llm:ocr_correction")
            else:
                value = field
                confidence = 0.62
                source = "llm:ocr_correction"

            if self._is_empty_value(value):
                continue

            raw_value = value
            extra: dict[str, Any] = {}
            if normalized_name == "total_amount":
                parsed_amount = self._parse_amount(str(value))
                if parsed_amount is None:
                    continue
                value = parsed_amount
                extra.update(
                    {
                        "raw": str(raw_value),
                        "currency": self._detect_currency(str(raw_value)),
                    }
                )

            confidence = self._safe_llm_confidence(confidence, default=0.62)
            existing = existing_fields.get(normalized_name)
            if existing and not self._should_replace_with_llm(
                normalized_name,
                existing,
                value,
                confidence,
            ):
                continue

            fields[normalized_name] = self._field(
                value,
                confidence,
                source,
                boxes,
                self._value_to_text(raw_value),
                extra,
            )

        return fields

    def _answer_field_from_llm_fields(
        self,
        field_name: str,
        analysis: dict[str, Any],
        existing_field: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        llm_fields = analysis.get("llm_fields")
        if not isinstance(llm_fields, dict):
            llm = analysis.get("llm") or {}
            llm_fields = llm.get("fields") if isinstance(llm, dict) else {}
        if not isinstance(llm_fields, dict):
            return None

        candidate = None
        for raw_name, raw_field in llm_fields.items():
            if self._normalize_dynamic_field_name(str(raw_name)) == field_name:
                candidate = raw_field
                break
        if candidate is None:
            return None

        if isinstance(candidate, dict) and "value" in candidate:
            value = candidate.get("value")
            confidence = self._safe_llm_confidence(candidate.get("confidence"), default=0.62)
            source = str(candidate.get("source") or "llm:ocr_correction")
        else:
            value = candidate
            confidence = 0.62
            source = "llm:ocr_correction"

        if self._is_empty_value(value):
            return None

        display_value = value
        if field_name == "total_amount":
            parsed_amount = self._parse_amount(str(value))
            if parsed_amount is None:
                return None
            display_value = parsed_amount

        if existing_field and not self._should_replace_with_llm(
            field_name,
            existing_field,
            display_value,
            confidence,
        ):
            return None

        answer_field = {
            "value": display_value,
            "confidence": confidence,
            "source": source,
            "source_box_ids": [],
        }
        if field_name == "total_amount":
            answer_field["currency"] = self._detect_currency(str(value))
        return {
            "answer": self._humanize_field(field_name, answer_field),
            "matched_field": field_name,
            "source_box_ids": [],
        }

    def _should_replace_with_llm(
        self,
        field_name: str,
        existing_field: dict[str, Any],
        candidate_value: Any,
        candidate_confidence: float,
    ) -> bool:
        existing_confidence = self._safe_confidence(existing_field.get("confidence"), default=0.5)
        existing_source = str(existing_field.get("source", ""))
        existing_value = existing_field.get("value")

        if field_name == "total_amount" and existing_source == "regex:largest_amount":
            return True
        if existing_confidence <= 0.56 and candidate_confidence >= 0.55:
            return True
        if field_name == "invoice_number" and existing_source.startswith("regex:"):
            existing_text = self._normalize(str(existing_value or ""))
            candidate_text = str(candidate_value or "")
            label_like_values = {"date", "invoice", "invoice date", "due date", "no", "number"}
            if existing_text in label_like_values and any(char.isdigit() for char in candidate_text):
                return True
            if not any(char.isdigit() for char in str(existing_value or "")) and any(char.isdigit() for char in candidate_text):
                return True

        if existing_source.startswith("layoutxlm:") and candidate_confidence >= 0.55:
            if self._layoutxlm_rejection_reason(field_name, existing_value):
                return True
            if field_name == "total_amount" and existing_confidence <= 0.8:
                return True
            if field_name in {"primary_date", "invoice_number"} and existing_confidence <= 0.75:
                return True

        if existing_source.startswith("llm:"):
            return candidate_confidence >= existing_confidence
        return False

    def _should_replace_with_layoutxlm(
        self,
        existing_field: dict[str, Any],
        candidate_confidence: float,
    ) -> bool:
        existing_confidence = self._safe_confidence(
            existing_field.get("confidence"),
            default=0.5,
        )
        existing_source = str(existing_field.get("source", ""))

        if candidate_confidence >= 0.88 and existing_confidence <= 0.72:
            return True
        if (
            existing_source.startswith("generic_kv:")
            and candidate_confidence >= existing_confidence + 0.08
        ):
            return True
        return False

    def _needs_invoice_fields(self, document_type: str) -> bool:
        return document_type == "invoice"

    def _needs_financial_fields(self, document_type: str) -> bool:
        return document_type in {"invoice", "receipt"}

    def _field_allowed_for_document(self, field_name: str, document_type: str) -> bool:
        invoice_only_fields = {
            "invoice_number",
            "invoice_form",
            "invoice_symbol",
            "tax_codes",
            "amount_in_words",
            "ma_so_thue",
            "mst",
            "so_hoa_don",
            "hoa_don_so",
            "mau_so",
            "ky_hieu",
            "so_tien_bang_chu",
        }
        financial_fields = {
            "total_amount",
            "payment_method",
            "tong_tien",
            "tong_cong",
            "tong_thanh_toan",
            "amount_due",
            "balance_due",
            "hinh_thuc_thanh_toan",
            "phuong_thuc_thanh_toan",
        }

        if field_name in invoice_only_fields:
            return self._needs_invoice_fields(document_type)
        if field_name in financial_fields:
            return self._needs_financial_fields(document_type)
        return True

    def _should_replace_with_generic_field(
        self,
        field_name: str,
        existing_field: dict[str, Any],
        pair: dict[str, Any],
    ) -> bool:
        source = str(pair.get("source", ""))
        if not source.startswith(("section:", "layout:")):
            return False

        existing_value = existing_field.get("value")
        if isinstance(existing_value, list):
            return False

        existing_text = str(existing_value or "").strip()
        pair_text = str(pair.get("display_value") or pair.get("value", "")).strip()
        if not pair_text:
            return False
        if not existing_text:
            return True

        normalized_existing = self._normalize(existing_text)
        label_markers = {
            "invoice",
            "invoice #",
            "invoice no",
            "invoice number",
            "date",
            "due",
            "terms",
            "total",
            "amount",
            "qty",
            "rate",
            "bill to",
            "ship to",
            "payment method",
        }

        if field_name in {"buyer", "seller", "shipping_address", "billing_address"}:
            return any(marker == normalized_existing or marker in normalized_existing for marker in label_markers)

        if field_name == "invoice_number":
            return any(char.isdigit() for char in pair_text) and not any(char.isdigit() for char in existing_text)

        return False

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

        if document_type == "invoice" and "invoice_number" not in fields:
            warnings.append(
                {
                    "type": "missing_invoice_number",
                    "message": "Chưa tìm thấy số hóa đơn.",
                    "severity": "medium",
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

    def _normalize_dynamic_field_name(self, text: str) -> str:
        normalized = self._normalize(text)
        normalized = re.sub(r"[^\w\s-]", "", normalized, flags=re.UNICODE)
        normalized = re.sub(r"[\s-]+", "_", normalized).strip("_")
        return normalized[:80]

    def _value_to_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            return " ".join(self._value_to_text(item) for item in value)
        if isinstance(value, dict):
            return " ".join(f"{key} {self._value_to_text(item)}" for key, item in value.items())
        return str(value)

    def _is_empty_value(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, tuple, dict)):
            return len(value) == 0
        return False

    def _safe_confidence(self, value: Any, default: float = 0.62) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return default
        return round(max(0.0, min(confidence, 1.0)), 2)

    def _safe_llm_confidence(self, value: Any, default: float = 0.62) -> float:
        confidence = self._safe_confidence(value, default=default)
        if confidence <= 0:
            return default
        return confidence

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
