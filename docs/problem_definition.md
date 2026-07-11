# Problem Definition

## Business Context and Motivation

Organizations still receive invoices, receipts, contracts, forms, and scanned documents as images or PDFs. Manual data entry is slow, expensive, and error-prone, especially when documents contain tables, Vietnamese text, skewed scans, or mixed English/Vietnamese layouts.

This project builds a document-level OCR and information extraction system that converts document images/PDFs into usable text, structured fields, tables, exported files, and question-answering responses.

## Target Users and Stakeholders

- Accounting staff who need invoice totals, invoice numbers, buyers, sellers, tax codes, and line items.
- Operations teams who need to search or export scanned documents.
- Data entry teams who need faster document digitization.
- Developers who need a REST API for OCR and document intelligence.
- Managers who need monitoring metrics for latency and extraction quality.

## Problem Being Solved

The system reduces manual work by:

- Reading text from document images and PDFs.
- Preserving document layout where possible.
- Extracting important business fields.
- Detecting tables in invoice-like documents.
- Supporting Vietnamese and English document questions.
- Exporting OCR results to PDF and Word.
- Monitoring API latency and OCR quality over time.

## Why NLP Is Required

OCR alone returns words and bounding boxes. NLP is required to understand document-level meaning:

- Classify document type.
- Identify semantic fields such as buyer, seller, total amount, date, tax code, and invoice number.
- Normalize noisy OCR output.
- Summarize document content.
- Answer natural-language questions over the document.
- Route invoices/receipts to LayoutXLM extraction while leaving general documents on the generic OCR path.

## Success Metrics

Business metrics:

- Reduce manual data entry time per document.
- Reduce repeated checking of common invoice fields.
- Increase number of processed documents per hour.
- Lower rework caused by missing totals, invoice IDs, and buyer/seller information.

Technical metrics:

- OCR word confidence and low-confidence word ratio.
- Document type accuracy.
- Field extraction accuracy on annotated evaluation manifests.
- Table extraction success rate for invoice-like documents.
- API average latency and p95 latency.
- API error rate.
- Estimated OCR error rate before and after AI correction.
