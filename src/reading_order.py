from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any


def ordered_lines_from_structured(structured_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return OCR lines sorted by visual reading order."""

    return sort_lines_reading_order(lines_from_structured(structured_data))


def raw_text_from_structured(structured_data: dict[str, Any]) -> str:
    word_rows = word_rows_from_structured(structured_data)
    if word_rows:
        return _text_from_word_rows(word_rows)

    lines = ordered_lines_from_structured(structured_data)
    if not lines:
        return ""

    pages: dict[int, list[str]] = defaultdict(list)
    for line in lines:
        text = line.get("text", "").strip()
        if text:
            pages[int(line.get("page", 1))].append(text)

    return "\n\n".join(
        "\n".join(page_lines)
        for page_number, page_lines in sorted(pages.items())
        if page_lines
    ).strip()


def word_rows_from_structured(structured_data: dict[str, Any]) -> dict[int, list[list[dict[str, Any]]]]:
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for word in words_from_structured(structured_data):
        by_page[int(word.get("page", 1))].append(word)

    rows_by_page = {}
    for page_number, words in by_page.items():
        if words:
            rows_by_page[page_number] = _group_words_into_rows(words)
    return rows_by_page


def bounding_boxes_from_structured(structured_data: dict[str, Any]) -> list[dict[str, Any]]:
    boxes = []
    for box_id, line in enumerate(ordered_lines_from_structured(structured_data), start=1):
        if not _has_geometry(line):
            continue
        x1 = float(line["x1"])
        y1 = float(line["y1"])
        x2 = float(line["x2"])
        y2 = float(line["y2"])
        boxes.append(
            {
                "id": str(box_id),
                "x": x1 * 100,
                "y": y1 * 100,
                "width": (x2 - x1) * 100,
                "height": (y2 - y1) * 100,
                "label": line.get("text", ""),
                "type": "text",
            }
        )
    return boxes


def sort_lines_reading_order(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_page: dict[int, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for original_index, line in enumerate(lines):
        by_page[int(line.get("page", 1))].append((original_index, line))

    ordered: list[dict[str, Any]] = []
    for page_number in sorted(by_page):
        page_items = by_page[page_number]
        positioned = [(index, line) for index, line in page_items if _has_geometry(line)]
        unpositioned = [(index, line) for index, line in page_items if not _has_geometry(line)]

        if positioned:
            slope = _estimate_page_slope([line for _, line in positioned])
            ordered.extend(_sort_positioned_page(positioned, slope))

        ordered.extend(line for _, line in sorted(unpositioned, key=lambda item: item[0]))

    return ordered


def lines_from_structured(structured_data: dict[str, Any]) -> list[dict[str, Any]]:
    lines = []
    line_id = 1
    for page_index, page in enumerate(structured_data.get("pages", []), start=1):
        page_width, page_height = _page_dimensions(page)
        for block_index, block in enumerate(page.get("blocks", []), start=1):
            for line_index, line in enumerate(block.get("lines", []), start=1):
                words = [word for word in line.get("words", []) if word.get("value")]
                text = " ".join(word.get("value", "") for word in words).strip()
                if not text:
                    continue

                geom = line.get("geometry") or _union_geometry(words)
                item: dict[str, Any] = {
                    "id": f"line_{line_id}",
                    "text": text,
                    "page": page_index,
                    "block": block_index,
                    "line": line_index,
                    "page_width": page_width,
                    "page_height": page_height,
                    "_word_centers": _word_centers(words, page_width, page_height),
                }
                if geom:
                    x1, y1, x2, y2 = _geometry_to_tuple(geom)
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


def words_from_structured(structured_data: dict[str, Any]) -> list[dict[str, Any]]:
    words = []
    word_id = 1
    for page_index, page in enumerate(structured_data.get("pages", []), start=1):
        page_width, page_height = _page_dimensions(page)
        for block_index, block in enumerate(page.get("blocks", []), start=1):
            for line_index, line in enumerate(block.get("lines", []), start=1):
                for word_index, word in enumerate(line.get("words", []), start=1):
                    text = str(word.get("value", "")).strip()
                    geom = word.get("geometry")
                    if not text or not geom:
                        continue

                    x1, y1, x2, y2 = _geometry_to_tuple(geom)
                    words.append(
                        {
                            "id": f"word_{word_id}",
                            "text": text,
                            "page": page_index,
                            "block": block_index,
                            "line": line_index,
                            "word": word_index,
                            "page_width": page_width,
                            "page_height": page_height,
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
                    word_id += 1
    return words


def _text_from_word_rows(rows_by_page: dict[int, list[list[dict[str, Any]]]]) -> str:
    pages = []
    for page_number in sorted(rows_by_page):
        rows = []
        for row in rows_by_page[page_number]:
            text = " ".join(word["text"] for word in row if word.get("text")).strip()
            if text:
                rows.append(text)
        if rows:
            pages.append("\n".join(rows))
    return "\n\n".join(pages).strip()


def _group_words_into_rows(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    slope = _estimate_word_slope(words)
    heights = [
        float(word.get("height", 0.001)) * float(word.get("page_height", 1.0))
        for word in words
    ]
    median_height = median(heights) if heights else 0.001
    tolerance = max(median_height * 0.75, 7.0)

    enriched = []
    for original_index, word in enumerate(words):
        page_width = float(word.get("page_width", 1.0))
        page_height = float(word.get("page_height", 1.0))
        px = float(word["cx"]) * page_width
        py = float(word["cy"]) * page_height
        enriched.append(
            {
                "original_index": original_index,
                "word": word,
                "row_key": py - slope * px,
                "col_key": float(word["x1"]) * page_width,
            }
        )

    groups: list[list[dict[str, Any]]] = []
    for item in sorted(enriched, key=lambda value: (value["row_key"], value["col_key"])):
        matched = None
        for group in groups:
            group_row = sum(value["row_key"] for value in group) / len(group)
            if abs(item["row_key"] - group_row) <= tolerance:
                matched = group
                break
        if matched is None:
            groups.append([item])
        else:
            matched.append(item)

    rows = []
    for group in sorted(groups, key=lambda values: sum(item["row_key"] for item in values) / len(values)):
        group.sort(key=lambda value: (value["col_key"], value["original_index"]))
        rows.append([item["word"] for item in group])
    return rows


def _estimate_word_slope(words: list[dict[str, Any]]) -> float:
    by_original_line: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for word in words:
        key = (
            int(word.get("page", 1)),
            int(word.get("block", 1)),
            int(word.get("line", 1)),
        )
        by_original_line[key].append(word)

    slopes = []
    for line_words in by_original_line.values():
        line_words = sorted(line_words, key=lambda item: item["x1"])
        if len(line_words) < 2:
            continue

        page_width = float(line_words[0].get("page_width", 1.0))
        page_height = float(line_words[0].get("page_height", 1.0))
        x1 = float(line_words[0]["cx"]) * page_width
        y1 = float(line_words[0]["cy"]) * page_height
        x2 = float(line_words[-1]["cx"]) * page_width
        y2 = float(line_words[-1]["cy"]) * page_height
        dx = x2 - x1
        if dx < 25:
            continue

        slope = (y2 - y1) / dx
        if abs(slope) <= 0.35:
            slopes.append(slope)

    if not slopes:
        return 0.0
    return float(median(slopes))


def _sort_positioned_page(
    positioned: list[tuple[int, dict[str, Any]]],
    slope: float,
) -> list[dict[str, Any]]:
    heights = [
        float(line.get("height", 0.001)) * float(line.get("page_height", 1.0))
        for _, line in positioned
    ]
    median_height = median(heights) if heights else 0.001
    tolerance = max(median_height * 0.9, 8.0)

    enriched = []
    for original_index, line in positioned:
        page_width = float(line.get("page_width", 1.0))
        page_height = float(line.get("page_height", 1.0))
        px = float(line["cx"]) * page_width
        py = float(line["cy"]) * page_height
        row_key = py - slope * px
        col_key = float(line["x1"]) * page_width
        enriched.append(
            {
                "original_index": original_index,
                "line": line,
                "row_key": row_key,
                "col_key": col_key,
            }
        )

    groups: list[list[dict[str, Any]]] = []
    for item in sorted(enriched, key=lambda value: (value["row_key"], value["col_key"])):
        matched = None
        for group in groups:
            group_row = sum(value["row_key"] for value in group) / len(group)
            if abs(item["row_key"] - group_row) <= tolerance:
                matched = group
                break
        if matched is None:
            groups.append([item])
        else:
            matched.append(item)

    ordered = []
    for group in sorted(groups, key=lambda values: sum(item["row_key"] for item in values) / len(values)):
        group.sort(key=lambda value: (value["col_key"], value["original_index"]))
        ordered.extend(item["line"] for item in group)
    return ordered


def _estimate_page_slope(lines: list[dict[str, Any]]) -> float:
    slopes = []
    for line in lines:
        centers = sorted(line.get("_word_centers", []), key=lambda point: point[0])
        if len(centers) < 2:
            continue
        x1, y1 = centers[0]
        x2, y2 = centers[-1]
        dx = x2 - x1
        if dx < 30:
            continue
        slope = (y2 - y1) / dx
        if abs(slope) <= 0.35:
            slopes.append(slope)

    if not slopes:
        return 0.0
    return float(median(slopes))


def _has_geometry(line: dict[str, Any]) -> bool:
    return all(key in line for key in ("x1", "y1", "x2", "y2", "cx", "cy"))


def _page_dimensions(page: dict[str, Any]) -> tuple[float, float]:
    dimensions = page.get("dimensions") or page.get("dimension")
    if isinstance(dimensions, dict):
        width = dimensions.get("width") or dimensions.get("w")
        height = dimensions.get("height") or dimensions.get("h")
        if width and height:
            return float(width), float(height)

    if isinstance(dimensions, (list, tuple)) and len(dimensions) >= 2:
        height, width = dimensions[:2]
        if width and height:
            return float(width), float(height)

    return 1000.0, 1000.0


def _word_centers(
    words: list[dict[str, Any]],
    page_width: float,
    page_height: float,
) -> list[tuple[float, float]]:
    centers = []
    for word in words:
        geom = word.get("geometry")
        if not geom:
            continue
        x1, y1, x2, y2 = _geometry_to_tuple(geom)
        centers.append((((x1 + x2) / 2) * page_width, ((y1 + y2) / 2) * page_height))
    return centers


def _union_geometry(words: list[dict[str, Any]]) -> list[list[float]] | None:
    geometries = [word.get("geometry") for word in words if word.get("geometry")]
    if not geometries:
        return None

    x1_values, y1_values, x2_values, y2_values = [], [], [], []
    for geom in geometries:
        x1, y1, x2, y2 = _geometry_to_tuple(geom)
        x1_values.append(x1)
        y1_values.append(y1)
        x2_values.append(x2)
        y2_values.append(y2)
    return [[min(x1_values), min(y1_values)], [max(x2_values), max(y2_values)]]


def _geometry_to_tuple(geom: Any) -> tuple[float, float, float, float]:
    (x1, y1), (x2, y2) = geom
    return float(x1), float(y1), float(x2), float(y2)
