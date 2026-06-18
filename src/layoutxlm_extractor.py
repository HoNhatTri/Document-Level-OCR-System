from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class OptionalLayoutXLMExtractor:
    """Optional LayoutXLM/LayoutLMv2 field extractor.

    The OCR pipeline remains usable when the model, Transformers, or
    Detectron2 is unavailable. Model loading is delayed until the first
    invoice/receipt that has page images and OCR word boxes.
    """

    DISABLED_VALUES = {"0", "false", "none", "off", "disabled"}
    FIELD_MAP = {
        "COMPANY": "seller",
        "ADDRESS": "seller_address",
        "DATE": "primary_date",
        "TOTAL": "total_amount",
    }

    def __init__(self, model_path: str | Path | None = None):
        configured_path = model_path or os.getenv(
            "LAYOUTXLM_MODEL_PATH",
            "model/layoutxlm-sroie-mcocr",
        )
        self.model_path = Path(configured_path)
        self.enabled_by_config = (
            os.getenv("LAYOUTXLM_ENABLED", "true").strip().lower()
            not in self.DISABLED_VALUES
        )
        self.min_confidence = self._float_env("LAYOUTXLM_MIN_CONFIDENCE", 0.55)
        self.chunk_words = self._int_env("LAYOUTXLM_CHUNK_WORDS", 180)
        self.requested_device = os.getenv("LAYOUTXLM_DEVICE", "auto").strip().lower()

        self.processor = None
        self.model = None
        self.torch = None
        self.device = "cpu"
        self._load_attempted = False
        self._load_error = ""

    def status(self) -> dict[str, Any]:
        if not self.enabled_by_config:
            return self._status("disabled", "LayoutXLM is disabled by configuration.")
        if not self.model_path.exists():
            return self._status(
                "unavailable",
                f"LayoutXLM model directory was not found: {self.model_path}",
            )
        if self.model is not None:
            return self._status("ready", "LayoutXLM model is ready.")
        if self._load_error:
            return self._status("unavailable", self._load_error)
        return self._status("available", "LayoutXLM will be loaded when needed.")

    def extract(
        self,
        page_images: list[Any] | None,
        structured_data: dict[str, Any] | None,
        document_type: str,
    ) -> dict[str, Any]:
        if document_type not in {"invoice", "receipt"}:
            return {
                **self.status(),
                "status": "skipped",
                "message": "LayoutXLM is only applied to invoices and receipts.",
                "fields": {},
                "entities": [],
            }
        if not page_images:
            return {
                **self.status(),
                "status": "skipped",
                "message": "No OCR page image is available for LayoutXLM.",
                "fields": {},
                "entities": [],
            }
        if not self._ensure_loaded():
            return {
                **self.status(),
                "fields": {},
                "entities": [],
            }

        pages = (structured_data or {}).get("pages", [])
        entities: list[dict[str, Any]] = []
        try:
            for page_index, (image, page) in enumerate(zip(page_images, pages), start=1):
                words, boxes = self._page_words_and_boxes(page)
                if not words:
                    continue
                entities.extend(
                    self._predict_page(
                        image=image,
                        words=words,
                        boxes=boxes,
                        page_index=page_index,
                    )
                )
        except Exception as exc:
            return {
                **self.status(),
                "status": "error",
                "message": f"LayoutXLM inference failed: {exc}",
                "fields": {},
                "entities": [],
            }

        accepted_entities = [
            entity
            for entity in entities
            if entity["confidence"] >= self.min_confidence
        ]
        fields = self._entities_to_fields(accepted_entities)
        return {
            **self.status(),
            "status": "ok",
            "message": f"LayoutXLM extracted {len(fields)} supplemental field(s).",
            "fields": fields,
            "entities": accepted_entities,
            "agent_trace": [
                "docTR words and normalized boxes were passed to LayoutXLM.",
                "BIO token labels were grouped into document entities.",
            ],
        }

    def _ensure_loaded(self) -> bool:
        if self.model is not None:
            return True
        if self._load_attempted or not self.enabled_by_config or not self.model_path.exists():
            return False

        self._load_attempted = True
        try:
            import torch
            from transformers import LayoutLMv2ForTokenClassification, LayoutXLMProcessor

            self.torch = torch
            self.device = self._resolve_device(torch)
            self.processor = LayoutXLMProcessor.from_pretrained(
                self.model_path,
                local_files_only=True,
                apply_ocr=False,
                fix_mistral_regex=True,
            )
            self.model = LayoutLMv2ForTokenClassification.from_pretrained(
                self.model_path,
                local_files_only=True,
            )
            self.model.to(self.device)
            self.model.eval()
            return True
        except ImportError as exc:
            reason = " ".join(str(exc).split())
            self._load_error = (
                f"LayoutXLM dependencies are unavailable: {reason}. "
                "LayoutLMv2 requires Transformers, SentencePiece, Safetensors, "
                "Torchvision, and Detectron2."
            )
        except Exception as exc:
            reason = " ".join(str(exc).split())
            self._load_error = f"Cannot load LayoutXLM model: {reason}"

        self.processor = None
        self.model = None
        return False

    def _predict_page(
        self,
        image: Any,
        words: list[str],
        boxes: list[list[int]],
        page_index: int,
    ) -> list[dict[str, Any]]:
        predictions: list[dict[str, Any]] = []
        for start in range(0, len(words), self.chunk_words):
            chunk_words = words[start : start + self.chunk_words]
            chunk_boxes = boxes[start : start + self.chunk_words]
            encoding = self.processor(
                images=image,
                text=chunk_words,
                boxes=chunk_boxes,
                truncation=True,
                padding="max_length",
                max_length=512,
                return_tensors="pt",
            )
            word_ids = encoding.word_ids(batch_index=0)
            model_inputs = {
                key: value.to(self.device)
                for key, value in encoding.items()
                if hasattr(value, "to")
            }

            with self.torch.inference_mode():
                logits = self.model(**model_inputs).logits[0]
                probabilities = self.torch.softmax(logits, dim=-1)
                confidences, label_ids = probabilities.max(dim=-1)

            seen_word_ids: set[int] = set()
            for token_index, word_id in enumerate(word_ids):
                if word_id is None or word_id in seen_word_ids or word_id >= len(chunk_words):
                    continue
                seen_word_ids.add(word_id)
                label_id = int(label_ids[token_index].item())
                label = str(self.model.config.id2label.get(label_id, "O"))
                predictions.append(
                    {
                        "word": chunk_words[word_id],
                        "box": chunk_boxes[word_id],
                        "label": label,
                        "confidence": float(confidences[token_index].item()),
                        "page": page_index,
                    }
                )

        return self._group_bio_entities(predictions)

    def _group_bio_entities(
        self,
        predictions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None

        def flush() -> None:
            nonlocal current
            if not current:
                return
            current["value"] = " ".join(current.pop("words")).strip()
            scores = current.pop("scores")
            current["confidence"] = round(sum(scores) / len(scores), 4)
            current["box"] = self._union_boxes(current.pop("boxes"))
            entities.append(current)
            current = None

        for item in predictions:
            label = item["label"]
            if label == "O" or "-" not in label:
                flush()
                continue

            prefix, entity_type = label.split("-", 1)
            starts_new = (
                prefix == "B"
                or current is None
                or current["label"] != entity_type
                or current["page"] != item["page"]
            )
            if starts_new:
                flush()
                current = {
                    "label": entity_type,
                    "page": item["page"],
                    "words": [],
                    "scores": [],
                    "boxes": [],
                }

            current["words"].append(item["word"])
            current["scores"].append(item["confidence"])
            current["boxes"].append(item["box"])

        flush()
        return entities

    def _entities_to_fields(
        self,
        entities: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        fields: dict[str, dict[str, Any]] = {}
        for entity in entities:
            field_name = self.FIELD_MAP.get(entity["label"])
            if not field_name:
                continue
            candidate = {
                "value": entity["value"],
                "confidence": entity["confidence"],
                "source": f"layoutxlm:{entity['label'].lower()}",
                "page": entity["page"],
                "box": entity["box"],
            }
            existing = fields.get(field_name)
            if not existing or candidate["confidence"] > existing["confidence"]:
                fields[field_name] = candidate
        return fields

    def _page_words_and_boxes(
        self,
        page: dict[str, Any],
    ) -> tuple[list[str], list[list[int]]]:
        words: list[str] = []
        boxes: list[list[int]] = []
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                for word in line.get("words", []):
                    value = str(word.get("value", "")).strip()
                    if not value:
                        continue
                    geometry = word.get("geometry") or line.get("geometry")
                    normalized_box = self._normalize_box(geometry)
                    if normalized_box is None:
                        continue
                    words.append(value)
                    boxes.append(normalized_box)
        return words, boxes

    def _normalize_box(self, geometry: Any) -> list[int] | None:
        try:
            x0, y0 = geometry[0]
            x1, y1 = geometry[1]
            values = [
                round(float(x0) * 1000),
                round(float(y0) * 1000),
                round(float(x1) * 1000),
                round(float(y1) * 1000),
            ]
        except (TypeError, ValueError, IndexError):
            return None

        values = [max(0, min(int(value), 1000)) for value in values]
        values[2] = max(values[0], values[2])
        values[3] = max(values[1], values[3])
        return values

    def _union_boxes(self, boxes: list[list[int]]) -> list[int]:
        return [
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        ]

    def _resolve_device(self, torch: Any) -> str:
        if self.requested_device == "cuda":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if self.requested_device == "cpu":
            return "cpu"
        return "cuda" if torch.cuda.is_available() else "cpu"

    def _status(self, status: str, message: str) -> dict[str, Any]:
        return {
            "status": status,
            "model": str(self.model_path),
            "device": self.device,
            "message": message,
        }

    def _float_env(self, key: str, default: float) -> float:
        try:
            return max(0.0, min(float(os.getenv(key, str(default))), 1.0))
        except ValueError:
            return default

    def _int_env(self, key: str, default: int) -> int:
        try:
            return max(32, int(os.getenv(key, str(default))))
        except ValueError:
            return default
