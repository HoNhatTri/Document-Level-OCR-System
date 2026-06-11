from src.layout_analyzer import LayoutAnalyzer
from tests.test_table_extractor import make_line


def test_detect_invoice_layout_regions():
    structured_data = {
        "pages": [
            {
                "blocks": [
                    {
                        "lines": [
                            make_line("INVOICE", 0.40, 0.05, 0.60, 0.08),
                            make_line("Date: 10/06/2026", 0.72, 0.10, 0.92, 0.12),
                            make_line("Invoice No: HD-00123", 0.72, 0.13, 0.94, 0.15),
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
                            make_line("Sub Total", 0.78, 0.65, 0.86, 0.67),
                            make_line("$899.00", 0.91, 0.65, 0.99, 0.67),
                            make_line("Authorized Signature", 0.68, 0.86, 0.92, 0.89),
                        ]
                    }
                ]
            }
        ]
    }

    regions = LayoutAnalyzer().analyze(structured_data)
    region_types = {region["type"] for region in regions}

    assert "title" in region_types
    assert "table" in region_types
    assert "total" in region_types
    assert "signature" in region_types

    table = next(region for region in regions if region["type"] == "table")
    assert table["label"] == "Danh sách sản phẩm"
    assert "Camera" in table["text"]
