from src.table_extractor import TableExtractor


def make_line(text, x1, y1, x2, y2):
    words = []
    tokens = text.split()
    width = max(x2 - x1, 0.001)
    token_width = width / max(len(tokens), 1)

    for index, token in enumerate(tokens):
        word_x1 = x1 + index * token_width
        word_x2 = min(x2, word_x1 + token_width * 0.85)
        words.append(
            {
                "value": token,
                "geometry": [[word_x1, y1], [word_x2, y2]],
                "confidence": 0.95,
            }
        )

    return {
        "geometry": [[x1, y1], [x2, y2]],
        "words": words,
    }


def test_extract_invoice_item_table():
    structured_data = {
        "pages": [
            {
                "blocks": [
                    {
                        "lines": [
                            make_line("#", 0.105, 0.20, 0.125, 0.22),
                            make_line("Item & Description", 0.17, 0.20, 0.34, 0.22),
                            make_line("Qty", 0.72, 0.20, 0.76, 0.22),
                            make_line("Rate", 0.82, 0.20, 0.87, 0.22),
                            make_line("Amount", 0.91, 0.20, 0.98, 0.22),
                            make_line("1", 0.108, 0.28, 0.122, 0.30),
                            make_line("Camera", 0.17, 0.28, 0.25, 0.30),
                            make_line("DSLR camera with advanced shooting capabilities", 0.17, 0.315, 0.50, 0.335),
                            make_line("1.00", 0.72, 0.28, 0.76, 0.30),
                            make_line("$899.00", 0.82, 0.28, 0.87, 0.30),
                            make_line("899.00", 0.92, 0.28, 0.98, 0.30),
                            make_line("2", 0.108, 0.40, 0.122, 0.42),
                            make_line("Fitness Tracker", 0.17, 0.40, 0.31, 0.42),
                            make_line("Activity tracker with heart rate monitoring", 0.17, 0.435, 0.48, 0.455),
                            make_line("1.00", 0.72, 0.40, 0.76, 0.42),
                            make_line("$129.00", 0.82, 0.40, 0.87, 0.42),
                            make_line("$129.00", 0.92, 0.40, 0.98, 0.42),
                            make_line("3", 0.108, 0.52, 0.122, 0.54),
                            make_line("Laptop", 0.17, 0.52, 0.24, 0.54),
                            make_line("Lightweight laptop with a powerful processor", 0.17, 0.555, 0.50, 0.575),
                            make_line("1.00", 0.72, 0.52, 0.76, 0.54),
                            make_line("$1.199.00", 0.82, 0.52, 0.89, 0.54),
                            make_line("$1.199.00", 0.92, 0.52, 0.99, 0.54),
                            make_line("Sub Total", 0.78, 0.65, 0.86, 0.67),
                            make_line("$2,227.00", 0.91, 0.65, 0.99, 0.67),
                        ]
                    }
                ]
            }
        ]
    }

    tables = TableExtractor().extract_tables(structured_data)

    assert len(tables) == 1
    assert tables[0]["headers"] == ["#", "Item & Description", "Qty", "Rate", "Amount"]
    assert len(tables[0]["rows"]) == 3
    assert tables[0]["rows"][0] == [
        "1",
        "Camera DSLR camera with advanced shooting capabilities",
        "1.00",
        "$899.00",
        "899.00",
    ]
    assert tables[0]["rows"][2][1] == "Laptop Lightweight laptop with a powerful processor"


def test_extract_vietnamese_invoice_item_table():
    structured_data = {
        "pages": [
            {
                "blocks": [
                    {
                        "lines": [
                            make_line("STT", 0.07, 0.20, 0.11, 0.22),
                            make_line("Tên hàng hóa, dịch vụ", 0.14, 0.20, 0.38, 0.22),
                            make_line("ĐVT", 0.52, 0.20, 0.56, 0.22),
                            make_line("Số lượng", 0.62, 0.20, 0.70, 0.22),
                            make_line("Đơn giá", 0.74, 0.20, 0.82, 0.22),
                            make_line("Thành tiền", 0.86, 0.20, 0.96, 0.22),
                            make_line("1", 0.08, 0.28, 0.10, 0.30),
                            make_line("Máy ảnh", 0.14, 0.28, 0.22, 0.30),
                            make_line("Cái", 0.52, 0.28, 0.56, 0.30),
                            make_line("1", 0.64, 0.28, 0.66, 0.30),
                            make_line("899.000", 0.74, 0.28, 0.82, 0.30),
                            make_line("899.000", 0.87, 0.28, 0.96, 0.30),
                            make_line("2", 0.08, 0.36, 0.10, 0.38),
                            make_line("Laptop văn phòng", 0.14, 0.36, 0.31, 0.38),
                            make_line("Cái", 0.52, 0.36, 0.56, 0.38),
                            make_line("1", 0.64, 0.36, 0.66, 0.38),
                            make_line("1.199.000", 0.74, 0.36, 0.83, 0.38),
                            make_line("1.199.000", 0.87, 0.36, 0.97, 0.38),
                            make_line("Cộng tiền hàng", 0.74, 0.48, 0.86, 0.50),
                            make_line("2.098.000", 0.87, 0.48, 0.97, 0.50),
                        ]
                    }
                ]
            }
        ]
    }

    tables = TableExtractor().extract_tables(structured_data)

    assert len(tables) == 1
    assert tables[0]["headers"] == ["STT", "Tên hàng hóa, dịch vụ", "ĐVT", "Số lượng", "Đơn giá", "Thành tiền"]
    assert tables[0]["rows"][0] == ["1", "Máy ảnh", "Cái", "1", "899.000", "899.000"]
    assert tables[0]["rows"][1][1] == "Laptop văn phòng"
