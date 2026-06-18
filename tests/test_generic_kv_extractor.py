from src.generic_kv_extractor import GenericKVExtractor


def make_line(text, x1, y1, x2, y2):
    geometry = [[x1, y1], [x2, y2]]
    return {
        "geometry": geometry,
        "words": [
            {
                "value": text,
                "geometry": geometry,
                "confidence": 0.99,
            }
        ],
    }


def test_extract_unknown_label_next_line_pair():
    text = """
    Project Invoice
    Reference Code
    ZX-42
    Prepared By
    Alex Nguyen
    """

    result = GenericKVExtractor().extract(text)
    pairs = result["key_values"]

    assert any(pair["label"] == "Reference Code" and pair["value"] == "ZX-42" for pair in pairs)
    assert any(pair["label"] == "Prepared By" and pair["value"] == "Alex Nguyen" for pair in pairs)


def test_extract_bill_to_section():
    text = """
    Invoice# INV-000001
    Bill To
    Ms. Mary D. Dunton
    1324 Hinkle Lake Road
    Needham
    Ship To
    1324 Hinkle Lake Road
    """

    result = GenericKVExtractor().extract(text)
    buyer = next(pair for pair in result["key_values"] if pair.get("canonical") == "buyer")

    assert buyer["label"] == "Bill To"
    assert buyer["display_value"] == "Ms. Mary D. Dunton"


def test_bill_to_vertical_block_does_not_pair_with_right_column_invoice_number():
    structured_data = {
        "pages": [
            {
                "blocks": [
                    {
                        "lines": [
                            make_line("BILL TO:", 0.02, 0.03, 0.11, 0.06),
                            make_line("INVOICE #", 0.86, 0.04, 0.98, 0.07),
                            make_line("Company Name", 0.02, 0.09, 0.22, 0.13),
                            make_line("0000001", 0.91, 0.09, 0.98, 0.13),
                            make_line("Address", 0.02, 0.15, 0.13, 0.18),
                            make_line("DATE", 0.92, 0.15, 0.98, 0.18),
                            make_line("City", 0.02, 0.19, 0.08, 0.22),
                            make_line("12/31/20", 0.89, 0.19, 0.98, 0.22),
                            make_line("Country", 0.02, 0.23, 0.13, 0.26),
                            make_line("INVOICE DUE DATE", 0.78, 0.23, 0.98, 0.26),
                            make_line("Postal", 0.02, 0.27, 0.11, 0.30),
                            make_line("12/31/20", 0.89, 0.27, 0.98, 0.30),
                        ]
                    }
                ]
            }
        ]
    }

    result = GenericKVExtractor().extract("", structured_data)
    pairs = result["key_values"]
    buyer = next(pair for pair in pairs if pair.get("canonical") == "buyer")
    invoice_number = next(pair for pair in pairs if pair.get("canonical") == "invoice_number")

    assert buyer["display_value"] == "Company Name"
    assert "Address" in buyer["value"]
    assert "City" in buyer["value"]
    assert "Country" in buyer["value"]
    assert "Postal" in buyer["value"]
    assert invoice_number["display_value"] == "0000001"
    assert not any(pair["label"] == "Company Name" and "0000001" in pair["value"] for pair in pairs)
    assert not any(pair["label"] == "Address" and pair["display_value"] == "City" for pair in pairs)
