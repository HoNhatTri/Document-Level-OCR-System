from __future__ import annotations

import re
import unicodedata
from statistics import median
from typing import Any


class LayoutAnalyzer:
    """Detect document-level layout regions from OCR geometry.

    The analyzer is rule-based so it can run offline with the existing docTR
    output. It labels higher-level regions such as title, header, table,
    important invoice fields, totals, footer, signature area, paragraphs, and
    two-column areas when the layout supports it.
    """

    TABLE_KEYWORDS = [
        "#",
        "item",
        "description",
        "qty",
        "quantity",
        "stt",
        "ten hang",
        "hang hoa",
        "hang hoa dich vu",
        "dvt",
        "don vi tinh",
        "so luong",
        "don gia",
        "rate",
        "amount",
        "price",
        "thanh tien",
        "so luong",
        "don gia",
    ]
    TOTAL_KEYWORDS = [
        "sub total",
        "subtotal",
        "cong tien hang",
        "total",
        "grand total",
        "tong cong tien thanh toan",
        "balance",
        "amount due",
        "tong cong",
        "tong tien",
        "tien thue",
        "gtgt",
        "thanh toan",
    ]
    IMPORTANT_INFO_KEYWORDS = [
        "invoice",
        "hoa don",
        "receipt",
        "bien lai",
        "date",
        "ngay",
        "mst",
        "ma so thue",
        "tax",
        "mau so",
        "ky hieu",
        "so hoa don",
        "hoa don so",
        "hinh thuc thanh toan",
        "tai khoan",
        "email",
        "phone",
        "dien thoai",
        "sdt",
        "address",
        "dia chi",
        "buyer",
        "seller",
        "nguoi mua",
        "nguoi ban",
    ]
    SIGNATURE_KEYWORDS = [
        "signature",
        "signed",
        "authorized",
        "ky ten",
        "chu ky",
        "nguoi lap",
        "nguoi nhan",
        "nguoi giao",
    ]
    FOOTER_KEYWORDS = [
        "thank",
        "cam on",
        "terms",
        "conditions",
        "footer",
        "page",
        "trang",
    ]

    def analyze(
        self,
        structured_data: dict[str, Any],
        tables: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        regions: list[dict[str, Any]] = []

        for page_index, page in enumerate(structured_data.get("pages", []), start=1):
            lines = self._extract_lines(page)
            if not lines:
                continue

            page_regions = self._analyze_page(lines, page_index, tables or [])
            regions.extend(page_regions)

        return self._assign_ids(regions)

    def _analyze_page(
        self,
        lines: list[dict[str, Any]],
        page_index: int,
        tables: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        regions: list[dict[str, Any]] = []
        used_line_ids: set[str] = set()

        table_region = self._detect_table_region(lines, page_index, tables)
        if table_region:
            regions.append(table_region)
            used_line_ids.update(table_region.get("_line_ids", []))

        title_region = self._detect_title(lines, page_index)
        if title_region:
            regions.append(title_region)
            used_line_ids.update(title_region.get("_line_ids", []))

        header_region = self._detect_header(lines, page_index, table_region, used_line_ids)
        if header_region:
            regions.append(header_region)
            used_line_ids.update(header_region.get("_line_ids", []))

        important_regions = self._detect_important_info(lines, page_index, used_line_ids)
        regions.extend(important_regions)
        for region in important_regions:
            used_line_ids.update(region.get("_line_ids", []))

        total_region = self._detect_total(lines, page_index, used_line_ids)
        if total_region:
            regions.append(total_region)
            used_line_ids.update(total_region.get("_line_ids", []))

        signature_region = self._detect_signature(lines, page_index, used_line_ids)
        if signature_region:
            regions.append(signature_region)
            used_line_ids.update(signature_region.get("_line_ids", []))

        column_regions = self._detect_columns(lines, page_index, table_region, used_line_ids)
        regions.extend(column_regions)
        for region in column_regions:
            used_line_ids.update(region.get("_line_ids", []))

        paragraph_regions = self._detect_paragraphs(lines, page_index, used_line_ids)
        regions.extend(paragraph_regions)
        for region in paragraph_regions:
            used_line_ids.update(region.get("_line_ids", []))

        footer_region = self._detect_footer(lines, page_index, used_line_ids)
        if footer_region:
            regions.append(footer_region)

        return self._dedupe_regions(regions)

    def _detect_title(self, lines: list[dict[str, Any]], page_index: int) -> dict[str, Any] | None:
        top_lines = [line for line in lines if line["cy"] <= 0.28]
        if not top_lines:
            return None

        invoice_lines = [
            line
            for line in top_lines
            if any(keyword in line["normalized"] for keyword in ["invoice", "hoa don", "receipt", "bien lai"])
        ]
        if invoice_lines:
            selected = max(invoice_lines, key=lambda line: (line["height"], -line["y1"]))
        else:
            median_height = self._median_height(top_lines)
            title_candidates = [
                line
                for line in top_lines
                if line["height"] >= median_height * 1.15 or line["cy"] <= 0.12
            ]
            selected = max(title_candidates or top_lines[:3], key=lambda line: (line["height"], -line["y1"]))

        return self._region(
            "title",
            "Tiêu đề tài liệu",
            [selected],
            page_index,
            confidence=0.78 if invoice_lines else 0.62,
            source="layout_rule:title",
        )

    def _detect_header(
        self,
        lines: list[dict[str, Any]],
        page_index: int,
        table_region: dict[str, Any] | None,
        used_line_ids: set[str],
    ) -> dict[str, Any] | None:
        table_top = table_region["y"] / 100 if table_region else 0.30
        header_lines = [
            line
            for line in lines
            if line["y1"] < min(table_top, 0.34) and line["id"] not in used_line_ids
        ]
        if len(header_lines) < 2:
            return None

        return self._region(
            "header",
            "Vùng đầu trang",
            header_lines,
            page_index,
            confidence=0.72,
            source="layout_rule:top_before_table",
        )

    def _detect_table_region(
        self,
        lines: list[dict[str, Any]],
        page_index: int,
        tables: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        header_group = self._find_table_header_group(lines)
        if not header_group:
            if any(table.get("page") == page_index for table in tables):
                dense_lines = self._densest_middle_lines(lines)
                if dense_lines:
                    return self._region(
                        "table",
                        "Bảng dữ liệu",
                        dense_lines,
                        page_index,
                        confidence=0.58,
                        source="layout_rule:table_from_extractor",
                    )
            return None

        header_bottom = max(line["y2"] for line in header_group)
        table_lines = [line for line in header_group]
        for line in lines:
            if line["cy"] <= header_bottom:
                continue
            if self._is_total_line(line):
                break
            if line["cy"] - header_bottom > 0.62:
                break
            table_lines.append(line)

        if len(table_lines) <= len(header_group):
            return None

        return self._region(
            "table",
            "Danh sách sản phẩm",
            table_lines,
            page_index,
            confidence=0.86,
            source="layout_rule:table_header",
        )

    def _detect_important_info(
        self,
        lines: list[dict[str, Any]],
        page_index: int,
        used_line_ids: set[str],
    ) -> list[dict[str, Any]]:
        important_lines = [
            line
            for line in lines
            if line["id"] not in used_line_ids
            and any(keyword in line["normalized"] for keyword in self.IMPORTANT_INFO_KEYWORDS)
        ]
        if not important_lines:
            return []

        groups = self._group_nearby_lines(important_lines, y_gap=0.06, x_gap=0.35)
        regions = []
        for group in groups[:4]:
            regions.append(
                self._region(
                    "important_info",
                    "Vùng thông tin quan trọng",
                    group,
                    page_index,
                    confidence=0.76,
                    source="layout_rule:important_keywords",
                )
            )
        return regions

    def _detect_total(
        self,
        lines: list[dict[str, Any]],
        page_index: int,
        used_line_ids: set[str],
    ) -> dict[str, Any] | None:
        total_lines = [
            line
            for line in lines
            if line["id"] not in used_line_ids and self._is_total_line(line)
        ]
        if not total_lines:
            return None

        selected = []
        for total_line in total_lines:
            selected.append(total_line)
            same_row = [
                line
                for line in lines
                if line["id"] != total_line["id"] and abs(line["cy"] - total_line["cy"]) <= self._row_tolerance(lines)
            ]
            selected.extend(same_row)

        return self._region(
            "total",
            "Vùng tổng tiền",
            selected,
            page_index,
            confidence=0.84,
            source="layout_rule:total_keywords",
        )

    def _detect_signature(
        self,
        lines: list[dict[str, Any]],
        page_index: int,
        used_line_ids: set[str],
    ) -> dict[str, Any] | None:
        signature_lines = [
            line
            for line in lines
            if line["id"] not in used_line_ids
            and line["cy"] >= 0.50
            and any(keyword in line["normalized"] for keyword in self.SIGNATURE_KEYWORDS)
        ]
        if not signature_lines:
            return None

        expanded = self._expand_with_nearby_lines(lines, signature_lines, x_padding=0.18, y_padding=0.08)
        return self._region(
            "signature",
            "Vùng chữ ký",
            expanded,
            page_index,
            confidence=0.78,
            source="layout_rule:signature_keywords",
        )

    def _detect_columns(
        self,
        lines: list[dict[str, Any]],
        page_index: int,
        table_region: dict[str, Any] | None,
        used_line_ids: set[str],
    ) -> list[dict[str, Any]]:
        table_top = table_region["y"] / 100 if table_region else 0.70
        candidates = [
            line
            for line in lines
            if line["id"] not in used_line_ids and line["cy"] < table_top and 0.08 <= line["cy"] <= 0.60
        ]
        left = [line for line in candidates if line["cx"] < 0.47]
        right = [line for line in candidates if line["cx"] > 0.53]

        if len(left) < 2 or len(right) < 2:
            return []

        if not self._has_vertical_overlap(left, right):
            return []

        return [
            self._region(
                "left_column",
                "Cột trái",
                left,
                page_index,
                confidence=0.66,
                source="layout_rule:two_columns",
            ),
            self._region(
                "right_column",
                "Cột phải",
                right,
                page_index,
                confidence=0.66,
                source="layout_rule:two_columns",
            ),
        ]

    def _detect_paragraphs(
        self,
        lines: list[dict[str, Any]],
        page_index: int,
        used_line_ids: set[str],
    ) -> list[dict[str, Any]]:
        paragraph_candidates = [
            line
            for line in lines
            if line["id"] not in used_line_ids
            and len(line["text"].split()) >= 4
            and not self._is_total_line(line)
            and not any(keyword in line["normalized"] for keyword in self.TABLE_KEYWORDS)
        ]
        groups = self._group_nearby_lines(paragraph_candidates, y_gap=0.035, x_gap=0.12)
        regions = []
        for group in groups[:6]:
            if len(group) == 1 and len(group[0]["text"].split()) < 8:
                continue
            regions.append(
                self._region(
                    "paragraph",
                    "Đoạn văn",
                    group,
                    page_index,
                    confidence=0.58 + min(len(group), 4) * 0.05,
                    source="layout_rule:paragraph_group",
                )
            )
        return regions

    def _detect_footer(
        self,
        lines: list[dict[str, Any]],
        page_index: int,
        used_line_ids: set[str],
    ) -> dict[str, Any] | None:
        footer_lines = [
            line
            for line in lines
            if line["id"] not in used_line_ids
            and (
                line["cy"] >= 0.86
                or any(keyword in line["normalized"] for keyword in self.FOOTER_KEYWORDS)
            )
        ]
        if not footer_lines:
            return None

        return self._region(
            "footer",
            "Vùng chân trang",
            footer_lines,
            page_index,
            confidence=0.62,
            source="layout_rule:bottom_or_footer_keywords",
        )

    def _find_table_header_group(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups = self._cluster_lines_by_y(lines)
        best_group: list[dict[str, Any]] = []
        best_score = 0

        for group in groups:
            text = " ".join(line["normalized"] for line in group)
            score = sum(1 for keyword in self.TABLE_KEYWORDS if keyword in text)
            has_item = "item" in text or "description" in text or "hang hoa" in text
            has_amount = "amount" in text or "total" in text or "thanh tien" in text
            if has_item and has_amount:
                score += 2
            if score > best_score and group[0]["cy"] < 0.75:
                best_score = score
                best_group = group

        return best_group if best_score >= 3 else []

    def _cluster_lines_by_y(self, lines: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        tolerance = self._row_tolerance(lines)
        groups: list[list[dict[str, Any]]] = []

        for line in sorted(lines, key=lambda item: item["cy"]):
            matched_group = None
            for group in groups:
                group_cy = sum(item["cy"] for item in group) / len(group)
                if abs(line["cy"] - group_cy) <= tolerance:
                    matched_group = group
                    break

            if matched_group is None:
                groups.append([line])
            else:
                matched_group.append(line)

        for group in groups:
            group.sort(key=lambda item: item["x1"])
        return groups

    def _group_nearby_lines(
        self,
        lines: list[dict[str, Any]],
        y_gap: float,
        x_gap: float,
    ) -> list[list[dict[str, Any]]]:
        groups: list[list[dict[str, Any]]] = []
        sorted_lines = sorted(lines, key=lambda item: (item["y1"], item["x1"]))

        for line in sorted_lines:
            if not groups:
                groups.append([line])
                continue

            previous = groups[-1][-1]
            vertical_gap = line["y1"] - previous["y2"]
            horizontal_shift = abs(line["x1"] - previous["x1"])
            if vertical_gap <= y_gap and horizontal_shift <= x_gap:
                groups[-1].append(line)
            else:
                groups.append([line])

        return groups

    def _expand_with_nearby_lines(
        self,
        all_lines: list[dict[str, Any]],
        seed_lines: list[dict[str, Any]],
        x_padding: float,
        y_padding: float,
    ) -> list[dict[str, Any]]:
        x1, y1, x2, y2 = self._bbox_tuple(seed_lines)
        expanded = [
            line
            for line in all_lines
            if x1 - x_padding <= line["cx"] <= x2 + x_padding
            and y1 - y_padding <= line["cy"] <= y2 + y_padding
        ]
        return expanded or seed_lines

    def _densest_middle_lines(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        middle_lines = [line for line in lines if 0.18 <= line["cy"] <= 0.80]
        if len(middle_lines) < 3:
            return []
        return middle_lines

    def _is_total_line(self, line: dict[str, Any]) -> bool:
        return any(keyword in line["normalized"] for keyword in self.TOTAL_KEYWORDS)

    def _has_vertical_overlap(self, left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
        left_top, left_bottom = min(line["y1"] for line in left), max(line["y2"] for line in left)
        right_top, right_bottom = min(line["y1"] for line in right), max(line["y2"] for line in right)
        return min(left_bottom, right_bottom) - max(left_top, right_top) > 0.02

    def _extract_lines(self, page: dict[str, Any]) -> list[dict[str, Any]]:
        lines = []
        line_index = 1
        for block_index, block in enumerate(page.get("blocks", []), start=1):
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
                        "id": f"b{block_index}_l{line_index}",
                        "text": text,
                        "normalized": self._normalize(text),
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "cx": (x1 + x2) / 2,
                        "cy": (y1 + y2) / 2,
                        "width": max(x2 - x1, 0.001),
                        "height": max(y2 - y1, 0.001),
                    }
                )
                line_index += 1
        return lines

    def _region(
        self,
        region_type: str,
        label: str,
        lines: list[dict[str, Any]],
        page_index: int,
        confidence: float,
        source: str,
    ) -> dict[str, Any]:
        x1, y1, x2, y2 = self._bbox_tuple(lines)
        return {
            "type": region_type,
            "label": label,
            "page": page_index,
            "x": round(x1 * 100, 2),
            "y": round(y1 * 100, 2),
            "width": round((x2 - x1) * 100, 2),
            "height": round((y2 - y1) * 100, 2),
            "text": "\n".join(line["text"] for line in sorted(lines, key=lambda item: (item["y1"], item["x1"]))),
            "confidence": round(min(max(confidence, 0.0), 0.99), 2),
            "source": source,
            "_line_ids": [line["id"] for line in lines],
        }

    def _dedupe_regions(self, regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped = []
        for region in sorted(regions, key=lambda item: (item["page"], item["y"], item["x"])):
            if not region.get("_line_ids"):
                continue

            duplicate = False
            for existing in deduped:
                if existing["type"] != region["type"]:
                    continue
                if self._overlap_ratio(existing, region) > 0.85:
                    duplicate = True
                    break
            if not duplicate:
                deduped.append(region)
        return deduped

    def _assign_ids(self, regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        public_regions = []
        for index, region in enumerate(regions, start=1):
            clean_region = {key: value for key, value in region.items() if not key.startswith("_")}
            clean_region["id"] = f"layout_{index}"
            public_regions.append(clean_region)
        return public_regions

    def _overlap_ratio(self, first: dict[str, Any], second: dict[str, Any]) -> float:
        first_box = self._percent_region_to_tuple(first)
        second_box = self._percent_region_to_tuple(second)
        inter_x1 = max(first_box[0], second_box[0])
        inter_y1 = max(first_box[1], second_box[1])
        inter_x2 = min(first_box[2], second_box[2])
        inter_y2 = min(first_box[3], second_box[3])
        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0

        intersection = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        smaller = min(
            (first_box[2] - first_box[0]) * (first_box[3] - first_box[1]),
            (second_box[2] - second_box[0]) * (second_box[3] - second_box[1]),
        )
        return intersection / smaller if smaller else 0.0

    def _percent_region_to_tuple(self, region: dict[str, Any]) -> tuple[float, float, float, float]:
        x1 = region["x"] / 100
        y1 = region["y"] / 100
        return x1, y1, x1 + region["width"] / 100, y1 + region["height"] / 100

    def _bbox_tuple(self, lines: list[dict[str, Any]]) -> tuple[float, float, float, float]:
        return (
            min(line["x1"] for line in lines),
            min(line["y1"] for line in lines),
            max(line["x2"] for line in lines),
            max(line["y2"] for line in lines),
        )

    def _row_tolerance(self, lines: list[dict[str, Any]]) -> float:
        return max(self._median_height(lines) * 1.2, 0.008)

    def _median_height(self, lines: list[dict[str, Any]]) -> float:
        heights = [line["height"] for line in lines if line.get("height", 0) > 0]
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
        normalized = no_marks.replace("\u0111", "d")
        return re.sub(r"\s+", " ", normalized).strip()
