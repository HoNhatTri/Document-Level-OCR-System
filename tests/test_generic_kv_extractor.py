from src.generic_kv_extractor import GenericKVExtractor


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
