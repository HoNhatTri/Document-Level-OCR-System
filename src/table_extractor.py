from __future__ import annotations

import re
import unicodedata
from statistics import median
from typing import Any


class TableExtractor:
    """Extract simple invoice-like tables from docTR structured OCR output.

    The extractor is layout-based. It uses OCR word/line geometry to find a
    header row and then assigns words into columns and item rows. It is not a
    full table recognition model, but it covers common invoices with columns
    such as #, Item/Description, Qty, Rate, and Amount.
    """

    HEADER_KEYWORDS = {
        "#": ["#", "no", "no.", "stt", "id"],
        "Item & Description": [
            "item",
            "description",
            "desc",
            "product",
            "service",
            "hang hoa",
            "ten hang",
            "hang hoa dich vu",
            "ten hang hoa dich vu",
            "noi dung",
        ],
        "Unit": ["unit", "dvt", "don vi tinh", "don vi"],
        "Qty": ["qty", "quantity", "sl", "so luong"],
        "Rate": ["rate", "price", "unit price", "don gia"],
        "Amount": ["amount", "total", "thanh tien", "money", "tien hang"],
    }
    STOP_ROW_KEYWORDS = [
        "sub total",
        "subtotal",
        "cong tien hang",
        "tong cong",
        "tong cong tien thanh toan",
        "tong tien",
        "tien thue",
        "gtgt",
        "tax",
        "vat",
        "balance",
        "grand total",
    ]

    def extract_tables(self, structured_data: dict[str, Any]) -> list[dict[str, Any]]:
        tables = []

        for page_index, page in enumerate(structured_data.get("pages", []), start=1):
            lines = self._extract_lines(page)
            words = self._extract_words(page)
            if not lines or not words:
                continue

            groups = self._cluster_lines_by_y(lines)
            header_group = self._find_header_group(groups)
            if not header_group:
                continue

            columns = self._build_columns(header_group["lines"])
            columns = self._localize_headers(columns, header_group["normalized"])
            if len(columns) < 2:
                continue

            table_bottom = self._find_table_bottom(lines, header_group["bottom"])
            row_bands = self._build_row_bands(words, lines, columns, header_group["bottom"], table_bottom)
            rows = self._build_rows(words, columns, row_bands, header_group["bottom"])
            rows = [row for row in rows if any(cell.strip() for cell in row)]

            if rows:
                tables.append(
                    {
                        "id": f"table_{len(tables) + 1}",
                        "name": f"Detected table page {page_index}",
                        "headers": [column["header"] for column in columns],
                        "rows": rows,
                        "page": page_index,
                        "confidence": round(min(0.95, 0.55 + len(rows) * 0.08 + len(columns) * 0.04), 2),
                    }
                )

        return tables

    def _extract_lines(self, page: dict[str, Any]) -> list[dict[str, Any]]:
        lines = []
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                words = [word for word in line.get("words", []) if word.get("value")]
                text = " ".join(word.get("value", "") for word in words).strip()
                if not text:
                    continue

                geom = line.get("geometry") or self._union_geometry(words)
                if not geom:
                    continue

                x1, y1, x2, y2 = self._geometry_to_tuple(geom)
                lines.append(
                    {
                        "text": text,
                        "normalized": self._normalize(text),
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "cx": (x1 + x2) / 2,
                        "cy": (y1 + y2) / 2,
                        "height": max(y2 - y1, 0.001),
                    }
                )
        return lines

    def _extract_words(self, page: dict[str, Any]) -> list[dict[str, Any]]:
        words = []
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                for word in line.get("words", []):
                    text = str(word.get("value", "")).strip()
                    geom = word.get("geometry")
                    if not text or not geom:
                        continue

                    x1, y1, x2, y2 = self._geometry_to_tuple(geom)
                    words.append(
                        {
                            "text": text,
                            "normalized": self._normalize(text),
                            "x1": x1,
                            "y1": y1,
                            "x2": x2,
                            "y2": y2,
                            "cx": (x1 + x2) / 2,
                            "cy": (y1 + y2) / 2,
                            "height": max(y2 - y1, 0.001),
                        }
                    )
        return words

    def _cluster_lines_by_y(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tolerance = self._row_tolerance(lines)
        groups: list[dict[str, Any]] = []

        for line in sorted(lines, key=lambda item: item["cy"]):
            matched_group = None
            for group in groups:
                if abs(line["cy"] - group["cy"]) <= tolerance:
                    matched_group = group
                    break

            if matched_group is None:
                groups.append({"lines": [line], "cy": line["cy"]})
            else:
                matched_group["lines"].append(line)
                matched_group["cy"] = sum(item["cy"] for item in matched_group["lines"]) / len(matched_group["lines"])

        for group in groups:
            group["lines"].sort(key=lambda item: item["x1"])
            group["top"] = min(item["y1"] for item in group["lines"])
            group["bottom"] = max(item["y2"] for item in group["lines"])
            group["text"] = " ".join(item["text"] for item in group["lines"])
            group["normalized"] = self._normalize(group["text"])

        return groups

    def _find_header_group(self, groups: list[dict[str, Any]]) -> dict[str, Any] | None:
        candidates = []
        for group in groups:
            labels = set()
            for line in group["lines"]:
                label = self._canonical_header(line["text"])
                if label:
                    labels.add(label)

            group_text = group["normalized"]
            for label, keywords in self.HEADER_KEYWORDS.items():
                if any(keyword in group_text for keyword in keywords):
                    labels.add(label)

            score = len(labels)
            has_table_shape = "Item & Description" in labels and ("Qty" in labels or "Amount" in labels)
            if score >= 3 or has_table_shape:
                candidates.append((score, group))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], -item[1]["cy"]), reverse=True)
        return candidates[0][1]

    def _build_columns(self, header_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        columns = []
        seen = set()

        for line in sorted(header_lines, key=lambda item: item["x1"]):
            header = self._canonical_header(line["text"])
            if not header or header in seen:
                continue

            seen.add(header)
            columns.append(
                {
                    "header": header,
                    "x1": line["x1"],
                    "x2": line["x2"],
                    "cx": line["cx"],
                    "left": 0.0,
                    "right": 1.0,
                }
            )

        if len(columns) < 2:
            return columns

        margin = 0.015
        for index, column in enumerate(columns):
            if index == 0:
                column["left"] = 0.0 if column["header"] in {"#", "No"} else max(0.0, column["x1"] - margin)
            else:
                column["left"] = max(columns[index - 1]["right"], column["x1"] - margin)

            if index == len(columns) - 1:
                column["right"] = 1.0
            else:
                next_column = columns[index + 1]
                right = next_column["x1"] - margin
                if right <= column["left"]:
                    right = (column["cx"] + next_column["cx"]) / 2
                column["right"] = min(1.0, max(column["left"] + 0.005, right))

        return columns

    def _localize_headers(
        self,
        columns: list[dict[str, Any]],
        normalized_header_text: str,
    ) -> list[dict[str, Any]]:
        vietnamese_markers = [
            "stt",
            "ten hang",
            "hang hoa",
            "dvt",
            "don vi tinh",
            "so luong",
            "don gia",
            "thanh tien",
        ]
        if not any(marker in normalized_header_text for marker in vietnamese_markers):
            return columns

        labels = {
            "#": "STT",
            "Item & Description": "Tên hàng hóa, dịch vụ",
            "Unit": "ĐVT",
            "Qty": "Số lượng",
            "Rate": "Đơn giá",
            "Amount": "Thành tiền",
        }
        for column in columns:
            column["header"] = labels.get(column["header"], column["header"])
        return columns

    def _build_row_bands(
        self,
        words: list[dict[str, Any]],
        lines: list[dict[str, Any]],
        columns: list[dict[str, Any]],
        header_bottom: float,
        table_bottom: float,
    ) -> list[dict[str, float]]:
        first_column = columns[0]
        median_height = self._median_height(words)
        row_margin = max(median_height * 1.5, 0.006)

        anchors = []
        if first_column["header"] in {"#", "No", "STT"}:
            for word in words:
                if not (header_bottom < word["cy"] < table_bottom):
                    continue
                if not self._is_inside_column(word, first_column):
                    continue
                if re.fullmatch(r"\d{1,3}", word["text"].strip()):
                    anchors.append(word)

        anchors = self._dedupe_y_anchors(sorted(anchors, key=lambda item: item["cy"]))
        if anchors:
            bands = []
            for index, anchor in enumerate(anchors):
                top = max(header_bottom, anchor["cy"] - row_margin)
                if index + 1 < len(anchors):
                    bottom = anchors[index + 1]["cy"] - row_margin
                else:
                    bottom = table_bottom
                if bottom > top:
                    bands.append({"top": top, "bottom": bottom})
            return bands

        row_groups = [
            group
            for group in self._cluster_lines_by_y(lines)
            if group["cy"] > header_bottom and group["cy"] < table_bottom
        ]
        return [
            {"top": max(header_bottom, group["top"] - row_margin), "bottom": min(table_bottom, group["bottom"] + row_margin)}
            for group in row_groups
        ]

    def _build_rows(
        self,
        words: list[dict[str, Any]],
        columns: list[dict[str, Any]],
        row_bands: list[dict[str, float]],
        header_bottom: float,
    ) -> list[list[str]]:
        rows = []

        for band in row_bands:
            row_words = [
                word
                for word in words
                if word["cy"] > header_bottom and band["top"] <= word["cy"] < band["bottom"]
            ]
            if not row_words:
                continue

            row = []
            for column in columns:
                cell_words = [word for word in row_words if self._is_inside_column(word, column)]
                row.append(self._join_cell_words(cell_words))

            if self._is_stop_row(row):
                break
            rows.append(row)

        return rows

    def _find_table_bottom(self, lines: list[dict[str, Any]], header_bottom: float) -> float:
        candidate_bottom = 1.0
        for line in sorted(lines, key=lambda item: item["cy"]):
            if line["cy"] <= header_bottom:
                continue
            if any(keyword in line["normalized"] for keyword in self.STOP_ROW_KEYWORDS):
                candidate_bottom = line["y1"]
                break

        if candidate_bottom < 1.0:
            return candidate_bottom

        below_header = [line["y2"] for line in lines if line["cy"] > header_bottom]
        return max(below_header, default=1.0)

    def _canonical_header(self, text: str) -> str | None:
        normalized = self._normalize(text)
        compact = normalized.replace(" ", "")

        for label, keywords in self.HEADER_KEYWORDS.items():
            for keyword in keywords:
                if label == "#":
                    if compact in {"#", "no", "no.", "stt", "id"}:
                        return label
                elif keyword in normalized:
                    return label
        return None

    def _join_cell_words(self, words: list[dict[str, Any]]) -> str:
        if not words:
            return ""

        sorted_words = sorted(words, key=lambda item: (round(item["cy"], 3), item["x1"]))
        text = " ".join(word["text"] for word in sorted_words)
        text = re.sub(r"\s+", " ", text).strip()
        text = text.replace("$ ", "$")
        text = text.replace(" ,", ",").replace(" .", ".")
        return text

    def _is_stop_row(self, row: list[str]) -> bool:
        normalized = self._normalize(" ".join(row))
        return any(keyword in normalized for keyword in self.STOP_ROW_KEYWORDS)

    def _is_inside_column(self, word: dict[str, Any], column: dict[str, Any]) -> bool:
        return column["left"] <= word["cx"] < column["right"]

    def _dedupe_y_anchors(self, anchors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped = []
        for anchor in anchors:
            if deduped and abs(anchor["cy"] - deduped[-1]["cy"]) < max(anchor["height"] * 1.5, 0.01):
                continue
            deduped.append(anchor)
        return deduped

    def _row_tolerance(self, lines: list[dict[str, Any]]) -> float:
        return max(self._median_height(lines) * 1.1, 0.008)

    def _median_height(self, items: list[dict[str, Any]]) -> float:
        heights = [item["height"] for item in items if item.get("height", 0) > 0]
        return median(heights) if heights else 0.012

    def _geometry_to_tuple(self, geom: list[list[float]]) -> tuple[float, float, float, float]:
        (x1, y1), (x2, y2) = geom
        return float(x1), float(y1), float(x2), float(y2)

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

    def _normalize(self, text: str) -> str:
        decomposed = unicodedata.normalize("NFD", text.lower())
        no_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
        return no_marks.replace("\u0111", "d")
