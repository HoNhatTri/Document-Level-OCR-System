import os

os.environ.setdefault("AI_PROVIDER", "none")

from src.agent import DocumentAgent


class FakeLLMAgent:
    def analyze(self, extracted_text, base_analysis=None, generic_kv=None):
        return {
            "status": "ok",
            "provider": "fake",
            "model": "fake-model",
            "summary": "LLM summary",
            "full_corrected_text": "Corrected OCR text",
            "fields": {
                "custom_reference": {
                    "value": "ZX-42",
                    "confidence": 0.77,
                    "source": "llm:test",
                }
            },
            "agent_trace": ["fake analysis"],
        }

    def answer_question(self, question, extracted_text, analysis=None, generic_kv=None):
        return {
            "answer": "LLM fallback answer",
            "matched_field": "llm_answer",
            "source_box_ids": [],
            "confidence": 0.7,
        }


class FakeInvoiceFieldLLMAgent:
    def analyze(self, extracted_text, base_analysis=None, generic_kv=None):
        return {
            "status": "ok",
            "provider": "fake",
            "model": "fake-model",
            "summary": "",
            "full_corrected_text": "",
            "fields": {
                "invoice_number": {"value": "INV-999", "confidence": 0.9, "source": "llm:test"},
                "total_amount": {"value": 999, "confidence": 0.9, "source": "llm:test"},
                "reference_code": {"value": "REF-42", "confidence": 0.8, "source": "llm:test"},
            },
            "agent_trace": [],
        }

    def answer_question(self, question, extracted_text, analysis=None, generic_kv=None):
        return None


class FakeLayoutXLMExtractor:
    def extract(self, page_images, structured_data, document_type):
        return {
            "status": "ok",
            "model": "fake-layoutxlm",
            "device": "cpu",
            "message": "fake extraction",
            "fields": {
                "seller": {
                    "value": "Zylker Electronics Hub",
                    "confidence": 0.94,
                    "source": "layoutxlm:company",
                },
                "seller_address": {
                    "value": "14B Northern Street",
                    "confidence": 0.9,
                    "source": "layoutxlm:address",
                },
            },
            "entities": [],
        }


def make_structured_line(text, x1, y1, x2, y2):
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


def test_agent_extracts_invoice_fields():
    agent = DocumentAgent()
    text = """
    HOA DON VAT
    So: HD-00123
    Ngay 10/06/2026
    MST: 0312345678
    Tong tien thanh toan: 1.250.000 VND
    Email: sales@example.com
    """

    result = agent.analyze(text)

    assert result["document_type"] == "invoice"
    assert result["fields"]["invoice_number"]["value"] == "HD-00123"
    assert result["fields"]["tax_codes"]["value"] == ["0312345678"]
    assert result["fields"]["primary_date"]["value"] == "10/06/2026"
    assert result["fields"]["total_amount"]["value"] == 1250000
    assert result["fields"]["emails"]["value"] == ["sales@example.com"]


def test_agent_answers_total_amount_question():
    agent = DocumentAgent()
    text = "Bien lai\nTong cong: 300,000 VND"
    analysis = agent.analyze(text)

    answer = agent.answer_question("Tong tien la bao nhieu?", text, analysis=analysis)

    assert answer["matched_field"] == "total_amount"
    assert "300000" in answer["answer"]


def test_agent_does_not_extract_invoice_fields_for_general_document():
    agent = DocumentAgent()
    text = """
    Project status report
    No: ABC123
    Total participants: 1,000
    Prepared by: Alex
    """

    result = agent.analyze(text)

    assert result["document_type"] == "general_document"
    assert "invoice_number" not in result["fields"]
    assert "total_amount" not in result["fields"]
    assert not any(warning["type"] == "missing_total_amount" for warning in result["warnings"])
    assert not any(warning["type"] == "missing_invoice_number" for warning in result["warnings"])


def test_agent_does_not_classify_article_that_mentions_invoices_as_invoice():
    agent = DocumentAgent()
    text = """
    Optical character recognition or optical character reader (OCR) is the electronic
    conversion of images of typed, handwritten or printed text into machine-encoded text.
    Widely used as a form of data entry from printed paper data records - whether passport documents,
    invoices, bank statements, computerized receipts, business cards, mail, printouts of static-data,
    or any suitable documentation - it is a common method of digitizing printed texts.
    """

    result = agent.analyze(text)

    assert result["document_type"] == "general_document"
    assert "invoice_number" not in result["fields"]
    assert "total_amount" not in result["fields"]


def test_agent_extracts_vietnamese_invoice_fields():
    agent = DocumentAgent()
    text = """
    HÓA ĐƠN GIÁ TRỊ GIA TĂNG
    Mẫu số: 01GTKT0/001
    Ký hiệu: AA/26E
    Số hóa đơn: 0000123
    Đơn vị bán hàng: Công ty TNHH Minh An
    Mã số thuế: 0312345678
    Người mua hàng: Nguyễn Văn A
    Hình thức thanh toán: Chuyển khoản
    Tổng cộng tiền thanh toán: 2.227.000 VND
    """

    result = agent.analyze(text)

    assert result["document_type"] == "invoice"
    assert result["fields"]["invoice_form"]["value"] == "01GTKT0/001"
    assert result["fields"]["invoice_symbol"]["value"] == "AA/26E"
    assert result["fields"]["invoice_number"]["value"] == "0000123"
    assert result["fields"]["seller"]["value"] == "Công ty TNHH Minh An"
    assert result["fields"]["buyer"]["value"] == "Nguyễn Văn A"
    assert result["fields"]["payment_method"]["value"] == "Chuyển khoản"
    assert result["fields"]["total_amount"]["value"] == 2227000
    assert "Tài liệu" in result["summary"]


def test_agent_answers_vietnamese_invoice_questions():
    agent = DocumentAgent()
    text = """
    HÓA ĐƠN GIÁ TRỊ GIA TĂNG
    Người mua hàng: Nguyễn Văn A
    Hình thức thanh toán: Chuyển khoản
    Tổng cộng tiền thanh toán: 2.227.000 VND
    """
    analysis = agent.analyze(text)

    buyer_answer = agent.answer_question("Ai là bên mua?", text, analysis=analysis)
    payment_answer = agent.answer_question("Hình thức thanh toán là gì?", text, analysis=analysis)
    summary_answer = agent.answer_question("Tài liệu này nói về nội dung gì?", text, analysis=analysis)

    assert buyer_answer["matched_field"] == "buyer"
    assert "Nguyễn Văn A" in buyer_answer["answer"]
    assert payment_answer["matched_field"] == "payment_method"
    assert "Chuyển khoản" in payment_answer["answer"]
    assert summary_answer["matched_field"] == "summary"


def test_agent_answers_buyer_from_ocr_lines_when_field_missing():
    agent = DocumentAgent()
    text = """
    HÓA ĐƠN GIÁ TRỊ GIA TĂNG
    Người mua hàng
    Nguyễn Văn A
    Mã số thuế: 0312345678
    """

    answer = agent.answer_question(
        "Ai là bên mua?",
        text,
        analysis={"fields": {}, "summary": ""},
    )

    assert answer["matched_field"] == "buyer"
    assert answer["answer"] == "Nguyễn Văn A"


def test_agent_answers_buyer_from_bill_to_block():
    agent = DocumentAgent()
    text = """
    Zylker Electronics Hub
    Invoice# INV-000001
    Bill To
    Ms. Mary D. Dunton
    1324 Hinkle Lake Road
    Needham
    02192 Maine
    Ship To
    1324 Hinkle Lake Road
    """

    analysis = agent.analyze(text)
    answer = agent.answer_question("Ai là bên mua?", text, analysis=analysis)

    assert analysis["fields"]["buyer"]["value"] == "Ms. Mary D. Dunton"
    assert answer["matched_field"] == "buyer"
    assert "Ms. Mary D. Dunton" in answer["answer"]


def test_agent_extracts_buyer_from_vertical_bill_to_block_with_right_invoice_column():
    agent = DocumentAgent()
    text = """
    BILL TO:
    INVOICE #
    Company Name
    0000001
    Address
    DATE
    City
    12/31/20
    Country
    INVOICE DUE DATE
    Postal
    12/31/20
    """
    structured_data = {
        "pages": [
            {
                "blocks": [
                    {
                        "lines": [
                            make_structured_line("BILL TO:", 0.02, 0.03, 0.11, 0.06),
                            make_structured_line("INVOICE #", 0.86, 0.04, 0.98, 0.07),
                            make_structured_line("Company Name", 0.02, 0.09, 0.22, 0.13),
                            make_structured_line("0000001", 0.91, 0.09, 0.98, 0.13),
                            make_structured_line("Address", 0.02, 0.15, 0.13, 0.18),
                            make_structured_line("DATE", 0.92, 0.15, 0.98, 0.18),
                            make_structured_line("City", 0.02, 0.19, 0.08, 0.22),
                            make_structured_line("12/31/20", 0.89, 0.19, 0.98, 0.22),
                            make_structured_line("Country", 0.02, 0.23, 0.13, 0.26),
                            make_structured_line("INVOICE DUE DATE", 0.78, 0.23, 0.98, 0.26),
                            make_structured_line("Postal", 0.02, 0.27, 0.11, 0.30),
                            make_structured_line("12/31/20", 0.89, 0.27, 0.98, 0.30),
                        ]
                    }
                ]
            }
        ]
    }

    analysis = agent.analyze(text, structured_data=structured_data)
    answer = agent.answer_question("Ai la ben mua?", text, analysis=analysis)

    assert analysis["fields"]["buyer"]["value"] == "Company Name"
    assert analysis["fields"]["buyer_address"]["value"] == "Address\nCity\nCountry\nPostal"
    assert analysis["fields"]["invoice_number"]["value"] == "0000001"
    assert answer["matched_field"] == "buyer"
    assert "Company Name" in answer["answer"]


def test_agent_answers_unknown_label_from_generic_kv():
    agent = DocumentAgent()
    text = """
    Project Invoice
    Reference Code
    ZX-42
    Prepared By
    Alex Nguyen
    """
    analysis = agent.analyze(text)

    answer = agent.answer_question("Reference Code là gì?", text, analysis=analysis)

    assert answer["matched_field"] == "generic_kv"
    assert answer["answer"] == "ZX-42"


def test_agent_merges_supplemental_llm_fields_without_api_call():
    agent = DocumentAgent(llm_agent=FakeLLMAgent())

    result = agent.analyze("Simple OCR text")

    assert result["llm"]["status"] == "ok"
    assert result["summary"] == "LLM summary"
    assert result["full_corrected_text"] == "Corrected OCR text"
    assert result["fields"]["custom_reference"]["value"] == "ZX-42"
    assert result["fields"]["custom_reference"]["source"] == "llm:test"


def test_agent_uses_llm_as_question_answering_fallback():
    agent = DocumentAgent(llm_agent=FakeLLMAgent())

    answer = agent.answer_question(
        "Cau hoi tu do?",
        "Simple OCR text",
        analysis={"fields": {}, "summary": "", "generic_kv": {}},
    )

    assert answer["matched_field"] == "llm_answer"
    assert answer["answer"] == "LLM fallback answer"


def test_agent_filters_invoice_llm_fields_for_general_document():
    agent = DocumentAgent(llm_agent=FakeInvoiceFieldLLMAgent())

    result = agent.analyze("Project status report\nNo: ABC123\nTotal participants: 1,000")

    assert result["document_type"] == "general_document"
    assert "invoice_number" not in result["fields"]
    assert "total_amount" not in result["fields"]
    assert result["fields"]["reference_code"]["value"] == "REF-42"


def test_agent_merges_layoutxlm_fields_without_replacing_pipeline():
    agent = DocumentAgent(layoutxlm_extractor=FakeLayoutXLMExtractor())
    text = """
    INVOICE
    Invoice #: INV-000001
    Total amount due: $2,338.35
    """

    result = agent.analyze(
        text,
        structured_data={"pages": []},
        page_images=[object()],
    )

    assert result["layoutxlm"]["status"] == "ok"
    assert result["fields"]["seller"]["value"] == "Zylker Electronics Hub"
    assert result["fields"]["seller"]["source"] == "layoutxlm:company"
    assert result["fields"]["seller_address"]["value"] == "14B Northern Street"
