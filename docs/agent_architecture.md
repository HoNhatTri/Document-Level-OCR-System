# Agent Architecture

## Agent Goal

The document agent turns OCR output into document-level intelligence. It classifies documents, extracts structured fields, detects uncertainty, routes special cases to optional models, and answers user questions.

## Components

- OCR engine: converts PDFs/images into text, structured words, and bounding boxes.
- Layout analyzer: detects titles, paragraphs, tables, totals, headers, footers, and important regions.
- Table extractor: reconstructs invoice-like item tables.
- Generic key-value extractor: detects unknown label-value pairs.
- Document agent: coordinates classification, field extraction, warnings, summary, and QA.
- Optional LayoutXLM extractor: improves invoice/receipt entity extraction.
- Optional LLM agent: corrects OCR text, adds diacritics, summarizes, and answers flexible questions.

## Decision Flow

```text
Upload document
  -> validate file type
  -> optional image preprocessing
  -> OCR with docTR
  -> extract text, boxes, structured JSON
  -> table extraction
  -> layout region detection
  -> agent classification
  -> deterministic field extraction
  -> generic key-value extraction
  -> if invoice/receipt, try LayoutXLM
  -> if LLM enabled, request correction and supplemental fields
  -> build warnings and quality metrics
  -> return Text/Table/JSON/AI views
```

## Pseudocode

```python
def analyze_document(file):
    raw_ocr = ocr_engine.process_document(file)
    structured = raw_ocr.export()
    text = reading_order.extract_text(structured)
    tables = table_extractor.extract_tables(structured)
    layout = layout_analyzer.analyze(structured, tables)

    document_type = agent.classify(text)
    fields = agent.extract_rules(text, structured)
    fields.update(generic_kv.extract(text, structured))

    if document_type in ["invoice", "receipt"]:
        fields.update(layoutxlm.extract(page_images, structured))

    if llm.enabled:
        fields.update(llm.correct_and_extract(text, fields))

    warnings = agent.build_warnings(structured, fields)
    return text, tables, layout, fields, warnings
```

## Example Interaction

Question:

```text
Ai là bên mua?
```

Agent decision:

1. Check extracted `buyer` field.
2. If missing, search `Bill To`, `Người mua`, `Đơn vị mua`, and nearby OCR lines.
3. If still missing and LLM is enabled, ask the LLM using only OCR context.
4. If no evidence exists, return that the information was not found.

## Agentic Behavior

The project includes agentic behavior because it:

- Makes routing decisions based on intermediate document type.
- Uses tools/models conditionally: rules, generic KV, LayoutXLM, LLM.
- Produces warnings when confidence is low or required fields are missing.
- Answers follow-up questions using extracted fields, OCR text, and fallback search.
