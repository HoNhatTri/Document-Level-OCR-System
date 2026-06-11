from src.agent import DocumentAgent


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
