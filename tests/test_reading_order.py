from src.reading_order import bounding_boxes_from_structured, raw_text_from_structured


def _word(value, x1, y1, x2, y2):
    return {"value": value, "geometry": [[x1, y1], [x2, y2]]}


def _line(text, x1, y1, x2, y2, word_y_step=0.0):
    words = [
        _word(
            part,
            x1 + index * 0.04,
            y1 + index * word_y_step,
            x1 + index * 0.04 + 0.03,
            y2 + index * word_y_step,
        )
        for index, part in enumerate(text.split())
    ]
    return {"geometry": [[x1, y1], [x2, y2]], "words": words}


def test_raw_text_is_sorted_by_visual_position():
    structured = {
        "pages": [
            {
                "dimensions": [1000, 1000],
                "blocks": [
                    {
                        "lines": [
                            _line("second row", 0.10, 0.22, 0.30, 0.25),
                            _line("right part", 0.55, 0.10, 0.75, 0.13),
                            _line("left part", 0.10, 0.10, 0.30, 0.13),
                        ]
                    }
                ],
            }
        ]
    }

    assert raw_text_from_structured(structured).splitlines() == [
        "left part right part",
        "second row",
    ]


def test_raw_text_compensates_for_light_skew_when_grouping_rows():
    structured = {
        "pages": [
            {
                "dimensions": [1000, 1000],
                "blocks": [
                    {
                        "lines": [
                            _line("bottom row", 0.10, 0.22, 0.35, 0.25, word_y_step=0.003),
                            _line("top right", 0.58, 0.14, 0.78, 0.17, word_y_step=0.003),
                            _line("top left", 0.10, 0.10, 0.30, 0.13, word_y_step=0.003),
                        ]
                    }
                ],
            }
        ]
    }

    assert raw_text_from_structured(structured).splitlines() == [
        "top left top right",
        "bottom row",
    ]


def test_raw_text_rebuilds_rows_from_jumbled_line_fragments():
    structured = {
        "pages": [
            {
                "dimensions": [1000, 1000],
                "blocks": [
                    {
                        "lines": [
                            _line("conversion of images", 0.10, 0.16, 0.34, 0.19, word_y_step=0.002),
                            _line("reader OCR is the", 0.52, 0.12, 0.78, 0.15, word_y_step=0.002),
                            _line("Optical character recognition", 0.10, 0.10, 0.42, 0.13, word_y_step=0.002),
                            _line("of typed text", 0.42, 0.18, 0.62, 0.21, word_y_step=0.002),
                        ]
                    }
                ],
            }
        ]
    }

    assert raw_text_from_structured(structured).splitlines() == [
        "Optical character recognition reader OCR is the",
        "conversion of images of typed text",
    ]


def test_bounding_boxes_follow_corrected_reading_order():
    structured = {
        "pages": [
            {
                "dimensions": [1000, 1000],
                "blocks": [
                    {
                        "lines": [
                            _line("B", 0.10, 0.20, 0.15, 0.23),
                            _line("A", 0.10, 0.10, 0.15, 0.13),
                        ]
                    }
                ],
            }
        ]
    }

    boxes = bounding_boxes_from_structured(structured)

    assert [box["label"] for box in boxes] == ["A", "B"]
    assert boxes[0]["id"] == "1"
