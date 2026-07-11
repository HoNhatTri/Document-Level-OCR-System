from src.monitoring import estimate_ocr_quality


def test_estimate_ocr_quality_tracks_ai_improvement():
    structured_data = {
        "pages": [
            {
                "blocks": [
                    {
                        "lines": [
                            {
                                "words": [
                                    {"value": "Invoice", "confidence": 0.98},
                                    {"value": "blurred", "confidence": 0.2},
                                    {"value": "total", "confidence": 0.5},
                                    {"value": "2338.35", "confidence": 0.99},
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    ai_analysis = {
        "document_type": "invoice",
        "fields": {
            "invoice_number": {"value": "INV-1"},
            "total_amount": {"value": 2338.35},
        },
        "warnings": [],
        "llm": {
            "status": "ok",
            "full_corrected_text": "Invoice total 2338.35",
        },
        "layoutxlm": {"status": "skipped"},
    }

    quality = estimate_ocr_quality(
        structured_data=structured_data,
        extracted_text="Invoice blurred total 2338.35",
        ai_analysis=ai_analysis,
    )

    assert quality["word_count"] == 4
    assert quality["low_confidence_word_count"] == 2
    assert quality["estimated_raw_error_rate"] == 0.5
    assert quality["estimated_after_ai_error_rate"] < quality["estimated_raw_error_rate"]
    assert quality["quality_level"] in {"good", "degraded", "poor"}
