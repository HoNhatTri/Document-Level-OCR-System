from __future__ import annotations

import re
import unicodedata
from statistics import median
from typing import Any


class GenericKVExtractor:
    """Generic label-value and section extractor for OCR text/layout.

    This module is deliberately schema-light. Instead of only looking for
    hard-coded fields, it extracts generic pairs such as "Invoice# -> INV-001",
    "Bill To -> Ms. Mary D. Dunton", or "Reference Code -> ZX-42". The agent
    can then answer new questions by matching the question to these labels.
    """

    SECTION_ALIASES = {
        "buyer": [
            "bill to",
            "billed to",
            "billing to",
            "sold to",
            "buyer",
            "customer",
            "client",
            "nguoi mua",
            "nguoi mua hang",
            "ben mua",
            "khach hang",
            "don vi mua",
        ],
        "seller": [
            "seller",
            "vendor",
            "from",
            "supplier",
            "nguoi ban",
            "ben ban",
            "don vi ban",
            "don vi ban hang",
        ],
        "shipping_address": [
            "ship to",
            "shipping to",
            "deliver to",
            "delivery address",
            "giao den",
            "dia chi giao hang",
        ],
        "billing_address": [
            "billing address",
            "bill address",
            "dia chi thanh toan",
        ],
    }

    STOP_LABELS = {
        "ship to",
        "shipping to",
        "bill to",
        "billed to",
        "billing to",
        "sold to",
        "invoice",
        "invoice #",
        "invoice number",
        "invoice#",
        "invoice no",
        "date",
        "invoice date",
        "terms",
        "due date",
        "payment method",
        "reference code",
        "prepared by",
        "approved by",
        "item",
        "item & description",
        "description",
        "qty",
        "rate",
        "amount",
        "total",
        "sub total",
        "subtotal",
        "tax",
        "balance due",
        "mau so",
        "ky hieu",
        "so hoa don",
        "ma so thue",
        "mst",
        "nguoi mua",
        "nguoi ban",
        "dia chi",
        "tong cong",
        "tong tien",
    }

    INLINE_SEPARATORS = [":", "："]
    LABEL_HINTS = {
        "code",
        "number",
        "no",
        "date",
        "terms",
        "due",
        "by",
        "method",
        "status",
        "reference",
        "prepared",
        "approved",
        "contact",
        "email",
        "phone",
        "tax",
        "total",
        "balance",
        "amount",
        "invoice",
        "payment",
        "address",
        "ma",
        "so",
        "ngay",
        "mau",
        "ky",
        "hieu",
        "thue",
        "thanh",
        "toan",
    }

    def extract(
        self,
        extracted_text: str,
        structured_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        lines = self._lines_from_structured(structured_data or {}) or self._lines_from_text(extracted_text)
        if any("cy" in line for line in lines):
            lines = sorted(lines, key=lambda item: (item.get("page", 1), item.get("cy", 0), item.get("x1", 0)))
        key_values: list[dict[str, Any]] = []

        key_values.extend(self._extract_inline_pairs(lines))
        key_values.extend(self._extract_row_pairs(lines))
        key_values.extend(self._extract_next_line_pairs(lines))

        key_values = self._dedupe_pairs(key_values)
        sections = [pair for pair in key_values if pair.get("source") == "section:next_lines"]

        return {
            "key_values": key_values,
            "sections": sections,
        }

    def find_by_field(
        self,
        field_name: str,
        generic_kv: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not generic_kv:
            return None

        canonical_map = {
            "buyer": ["buyer"],
            "seller": ["seller"],
            "shipping_address": ["shipping_address"],
            "buyer_address": ["buyer", "billing_address"],
            "seller_address": ["seller"],
            "payment_method": ["payment_method"],
            "invoice_number": ["invoice_number"],
            "invoice_form": ["invoice_form"],
            "invoice_symbol": ["invoice_symbol"],
        }
        canonical_targets = set(canonical_map.get(field_name, []))

        for pair in generic_kv.get("key_values", []):
            canonical = pair.get("canonical")
            if canonical in canonical_targets:
                return pair
        return None

    def answer_from_question(
        self,
        question: str,
        generic_kv: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not generic_kv:
            return None

        normalized_question = self._normalize(question)
        question_tokens = self._tokens(normalized_question)
        if not question_tokens:
            return None

        best_pair = None
        best_score = 0.0
        for pair in generic_kv.get("key_values", []):
            label = pair.get("label", "")
            normalized_label = self._normalize(label)
            label_tokens = self._tokens(normalized_label)
            if not label_tokens:
                continue

            token_overlap = len(question_tokens & label_tokens)
            phrase_bonus = 2 if normalized_label and normalized_label in normalized_question else 0
            canonical_bonus = 1.5 if pair.get("canonical") and pair["canonical"].replace("_", " ") in normalized_question else 0
            score = token_overlap + phrase_bonus + canonical_bonus

            if score > best_score:
                best_score = score
                best_pair = pair

        if best_pair and best_score >= 1.5:
            return {
                "answer": self._display_value(best_pair),
                "matched_field": best_pair.get("canonical") or "generic_kv",
                "source_box_ids": best_pair.get("source_box_ids", []),
            }
        return None

    def _extract_inline_pairs(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pairs = []
        for line in lines:
            split_pair = self._split_inline_pair(line["text"])
            if not split_pair:
                continue
            label, value = split_pair
            if not self._looks_like_label(label) or not value:
                continue
            pairs.append(self._pair(label, value, [line], "inline:separator", 0.72))
        return pairs

    def _extract_row_pairs(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not any("cy" in line for line in lines):
            return []

        pairs = []
        groups = self._cluster_by_y([line for line in lines if "cy" in line])
        for group in groups:
            if len(group) < 2:
                continue
            ordered = sorted(group, key=lambda item: item["x1"])
            label_line = ordered[0]
            value_lines = ordered[1:]
            label = label_line["text"].strip()
            value = " ".join(line["text"].strip() for line in value_lines if line["text"].strip())
            first_value_x = min(line.get("x1", 1.0) for line in value_lines)
            horizontal_gap = first_value_x - label_line.get("x2", label_line.get("x1", 0.0))
            if self._looks_like_row_label(label) and value and horizontal_gap <= 0.24:
                pairs.append(self._pair(label, value, group, "layout:same_row", 0.68))
        return pairs

    def _extract_next_line_pairs(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pairs = []
        covered_by_section: set[str] = set()
        for index, line in enumerate(lines):
            if line.get("id") in covered_by_section:
                continue

            label = line["text"].strip(" :-")
            normalized_label = self._normalize(label)
            if not self._looks_like_standalone_label(label):
                continue

            if "cy" in line:
                value_lines = self._next_value_lines_by_geometry(lines, index, line, normalized_label)
            else:
                value_lines = self._next_value_lines_by_order(lines, index, normalized_label)

            value = "\n".join(item["text"].strip() for item in value_lines if item["text"].strip()).strip()
            if value:
                pairs.append(self._pair(label, value, [line, *value_lines], "section:next_lines", 0.66))
                if self._canonical_for_label(normalized_label) in {
                    "buyer",
                    "seller",
                    "shipping_address",
                    "billing_address",
                }:
                    covered_by_section.update(item.get("id", "") for item in value_lines)
        return pairs

    def _next_value_lines_by_order(
        self,
        lines: list[dict[str, Any]],
        index: int,
        normalized_label: str,
    ) -> list[dict[str, Any]]:
        value_lines = []
        canonical = self._canonical_for_label(normalized_label)
        is_block = canonical in {"buyer", "seller", "shipping_address", "billing_address"}
        max_lines = 6 if is_block else 1
        for next_line in lines[index + 1 : index + 6]:
            text = next_line["text"].strip()
            if not text:
                continue
            if self._is_table_header(text):
                break
            if self._is_stop_label(text) and (value_lines or is_block):
                break
            if not is_block and self._looks_like_standalone_label(text) and value_lines:
                break
            value_lines.append(next_line)
            if len(value_lines) >= max_lines:
                break
        return value_lines

    def _next_value_lines_by_geometry(
        self,
        lines: list[dict[str, Any]],
        index: int,
        label_line: dict[str, Any],
        normalized_label: str,
    ) -> list[dict[str, Any]]:
        label_x1 = label_line.get("x1", 0.0)
        label_x2 = label_line.get("x2", label_x1)
        label_cx = label_line.get("cx", (label_x1 + label_x2) / 2)
        label_y = label_line.get("cy", 0.0)
        canonical = self._canonical_for_label(normalized_label)
        is_block = canonical in {"buyer", "seller", "shipping_address", "billing_address"}
        max_lines = 6 if is_block else 1

        if label_cx < 0.5:
            column_left = max(0.0, label_x1 - 0.08)
            column_right = min(0.58, max(label_x2 + 0.42, label_cx + 0.18))
        else:
            column_left = max(0.42, label_x1 - 0.18)
            column_right = min(1.0, label_x2 + 0.12)

        value_lines = []
        for candidate in lines[index + 1 :]:
            if candidate.get("page", 1) != label_line.get("page", 1):
                continue
            if "cy" not in candidate or candidate["cy"] <= label_y:
                continue
            if candidate["cy"] - label_y > (0.34 if is_block else 0.12):
                break

            text = candidate["text"].strip()
            if not text:
                continue
            candidate_cx = candidate.get("cx", 0.0)
            if not (column_left <= candidate_cx <= column_right):
                continue
            if self._is_table_header(text):
                break
            if self._is_stop_label(text) and (value_lines or is_block):
                break
            if not is_block and self._looks_like_standalone_label(text) and value_lines:
                break

            value_lines.append(candidate)
            if len(value_lines) >= max_lines:
                break

        return value_lines

    def _pair(
        self,
        label: str,
        value: str,
        lines: list[dict[str, Any]],
        source: str,
        confidence: float,
    ) -> dict[str, Any]:
        canonical = self._canonical_for_label(self._normalize(label))
        return {
            "label": label.strip(),
            "normalized_label": self._normalize(label),
            "canonical": canonical,
            "value": value.strip(),
            "display_value": self._first_value_line(value),
            "source": source,
            "confidence": round(confidence, 2),
            "page": lines[0].get("page", 1) if lines else 1,
            "bbox": self._bbox(lines),
            "source_box_ids": [],
        }

    def _split_inline_pair(self, text: str) -> tuple[str, str] | None:
        for separator in self.INLINE_SEPARATORS:
            if separator in text:
                label, value = text.split(separator, 1)
                return label.strip(), value.strip()

        match = re.match(r"^([A-Za-zÀ-ỹ0-9\s./&_-]{2,30})#\s*(.+)$", text)
        if match:
            return match.group(1).strip() + "#", match.group(2).strip()

        match = re.match(r"^(.{2,35}?)\s{2,}(.{2,})$", text)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return None

    def _looks_like_label(self, text: str) -> bool:
        cleaned = text.strip(" :-#")
        normalized = self._normalize(cleaned)
        if not cleaned or len(cleaned) > 45:
            return False
        if self._is_section_alias(normalized):
            return True
        if self._is_known_label(normalized):
            return True
        words = cleaned.split()
        if len(words) <= 5 and not self._mostly_numeric(cleaned) and self._has_label_hint(normalized):
            return True
        return False

    def _looks_like_row_label(self, text: str) -> bool:
        cleaned = text.strip(" :-#")
        normalized = self._normalize(cleaned)
        if not cleaned or len(cleaned) > 45 or self._mostly_numeric(cleaned):
            return False
        if self._is_section_alias(normalized) or self._is_known_label(normalized):
            return True
        return self._has_label_hint(normalized)

    def _looks_like_standalone_label(self, text: str) -> bool:
        cleaned = text.strip(" :-")
        normalized = self._normalize(cleaned)
        if not self._looks_like_label(cleaned):
            return False
        if self._split_inline_pair(text):
            return False
        if self._is_section_alias(normalized, exact=True):
            return True
        if self._is_known_label(normalized):
            return True
        return len(cleaned.split()) <= 4 and not any(char.isdigit() for char in cleaned) and self._has_label_hint(normalized)

    def _is_stop_label(self, text: str) -> bool:
        normalized = self._normalize(text.strip(" :-"))
        return self._is_known_label(normalized) or self._is_section_alias(normalized, exact=True)

    def _is_known_label(self, normalized: str) -> bool:
        return normalized in self.STOP_LABELS or any(label in normalized for label in self.STOP_LABELS if len(label) >= 4)

    def _is_section_alias(self, normalized: str, exact: bool = False) -> bool:
        for aliases in self.SECTION_ALIASES.values():
            for alias in aliases:
                if exact and alias == normalized:
                    return True
                if not exact and (alias == normalized or alias in normalized):
                    return True
        return False

    def _has_label_hint(self, normalized: str) -> bool:
        tokens = self._tokens(normalized)
        return bool(tokens & self.LABEL_HINTS)

    def _is_table_header(self, text: str) -> bool:
        normalized = self._normalize(text)
        table_markers = ["item", "description", "qty", "rate", "amount", "stt", "so luong", "don gia", "thanh tien"]
        return sum(marker in normalized for marker in table_markers) >= 2

    def _canonical_for_label(self, normalized_label: str) -> str | None:
        for canonical, aliases in self.SECTION_ALIASES.items():
            if any(alias == normalized_label or alias in normalized_label for alias in aliases):
                return canonical

        field_aliases = {
            "invoice_number": ["invoice#", "invoice #", "invoice no", "invoice number", "so hoa don", "hoa don so", "so hd"],
            "invoice_form": ["mau so", "form"],
            "invoice_symbol": ["ky hieu", "serial"],
            "payment_method": ["payment method", "hinh thuc thanh toan", "phuong thuc thanh toan"],
        }
        for canonical, aliases in field_aliases.items():
            if any(alias == normalized_label or alias in normalized_label for alias in aliases):
                return canonical
        return None

    def _display_value(self, pair: dict[str, Any]) -> str:
        return pair.get("display_value") or self._first_value_line(pair.get("value", ""))

    def _first_value_line(self, value: str) -> str:
        for line in value.splitlines():
            cleaned = line.strip()
            if cleaned:
                return cleaned
        return value.strip()

    def _dedupe_pairs(self, pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped = []
        seen = set()
        for pair in pairs:
            key = (pair["normalized_label"], self._normalize(pair["value"]))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(pair)
        return deduped

    def _cluster_by_y(self, lines: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        heights = [line.get("height", 0.01) for line in lines]
        tolerance = max(median(heights) * 1.1 if heights else 0.012, 0.008)
        groups: list[list[dict[str, Any]]] = []

        for line in sorted(lines, key=lambda item: item["cy"]):
            matched = None
            for group in groups:
                group_cy = sum(item["cy"] for item in group) / len(group)
                if abs(line["cy"] - group_cy) <= tolerance:
                    matched = group
                    break
            if matched is None:
                groups.append([line])
            else:
                matched.append(line)
        return groups

    def _lines_from_structured(self, structured_data: dict[str, Any]) -> list[dict[str, Any]]:
        lines = []
        line_id = 1
        for page_index, page in enumerate(structured_data.get("pages", []), start=1):
            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    words = [word for word in line.get("words", []) if word.get("value")]
                    text = " ".join(word.get("value", "") for word in words).strip()
                    if not text:
                        continue
                    geom = line.get("geometry") or self._union_geometry(words)
                    item = {
                        "id": f"line_{line_id}",
                        "text": text,
                        "page": page_index,
                    }
                    if geom:
                        x1, y1, x2, y2 = self._geometry_to_tuple(geom)
                        item.update(
                            {
                                "x1": x1,
                                "y1": y1,
                                "x2": x2,
                                "y2": y2,
                                "cx": (x1 + x2) / 2,
                                "cy": (y1 + y2) / 2,
                                "height": max(y2 - y1, 0.001),
                            }
                        )
                    lines.append(item)
                    line_id += 1
        return lines

    def _lines_from_text(self, text: str) -> list[dict[str, Any]]:
        return [
            {
                "id": f"line_{index + 1}",
                "text": line.strip(),
                "page": 1,
                "order": index,
            }
            for index, line in enumerate(text.splitlines())
            if line.strip()
        ]

    def _bbox(self, lines: list[dict[str, Any]]) -> dict[str, float] | None:
        positioned = [line for line in lines if all(key in line for key in ["x1", "y1", "x2", "y2"])]
        if not positioned:
            return None
        x1 = min(line["x1"] for line in positioned)
        y1 = min(line["y1"] for line in positioned)
        x2 = max(line["x2"] for line in positioned)
        y2 = max(line["y2"] for line in positioned)
        return {
            "x": round(x1 * 100, 2),
            "y": round(y1 * 100, 2),
            "width": round((x2 - x1) * 100, 2),
            "height": round((y2 - y1) * 100, 2),
        }

    def _union_geometry(self, words: list[dict[str, Any]]) -> list[list[float]] | None:
        geometries = [word.get("geometry") for word in words if word.get("geometry")]
        if not geometries:
            return None
        x1_values, y1_values, x2_values, y2_values = [], [], [], []
        for geom in geometries:
            x1, y1, x2, y2 = self._geometry_to_tuple(geom)
            x1_values.append(x1)
            y1_values.append(y1)
            x2_values.append(x2)
            y2_values.append(y2)
        return [[min(x1_values), min(y1_values)], [max(x2_values), max(y2_values)]]

    def _geometry_to_tuple(self, geom: list[list[float]]) -> tuple[float, float, float, float]:
        (x1, y1), (x2, y2) = geom
        return float(x1), float(y1), float(x2), float(y2)

    def _mostly_numeric(self, text: str) -> bool:
        chars = [char for char in text if not char.isspace()]
        if not chars:
            return False
        numeric = sum(char.isdigit() or char in ".,/$%-" for char in chars)
        return numeric / len(chars) > 0.65

    def _tokens(self, text: str) -> set[str]:
        stopwords = {"la", "gi", "ai", "cua", "trong", "nay", "what", "is", "the", "of", "this"}
        return {
            token
            for token in re.findall(r"[a-z0-9_#]+", text)
            if len(token) >= 2 and token not in stopwords
        }

    def _normalize(self, text: str) -> str:
        decomposed = unicodedata.normalize("NFD", text.lower())
        no_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
        normalized = no_marks.replace("\u0111", "d")
        return re.sub(r"\s+", " ", normalized).strip()
