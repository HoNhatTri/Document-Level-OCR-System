from __future__ import annotations

import os
import tempfile
from pathlib import Path

import cv2
import numpy as np

from src.settings import get_settings


class ImagePreprocessor:
    """Create OCR-friendly image copies without modifying the original file."""

    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

    def __init__(
        self,
        mode: str | None = None,
        target_width: int | None = None,
        min_width: int = 1200,
        max_width: int = 2400,
    ):
        self.mode = (mode or os.getenv("OCR_PREPROCESS_MODE", "auto")).strip().lower()
        self.target_width = target_width
        self.min_width = min_width
        self.max_width = max_width
        self.last_info: dict[str, object] = {
            "skew_detected": False,
            "skew_angle": None,
            "page_rectified": False,
            "special_handling": False,
        }

    def should_preprocess(self, file_path: str) -> bool:
        extension = Path(file_path).suffix.lower()
        if not get_settings().get("image_preprocessing_enabled", True):
            return False
        return self.mode not in {"", "none", "off", "false", "0"} and extension in self.IMAGE_EXTENSIONS

    def preprocess_to_temp_file(self, file_path: str) -> str:
        """Return a temporary PNG path for OCR. Caller owns cleanup."""

        image = self._read_image(file_path)
        processed = self.preprocess_array(image)

        fd, output_path = tempfile.mkstemp(prefix="ocr_preprocessed_", suffix=".png")
        os.close(fd)
        if not cv2.imwrite(output_path, processed):
            raise ValueError("Khong the ghi anh tien xu ly.")
        return output_path

    def preprocess_array(self, image: np.ndarray) -> np.ndarray:
        self.last_info = {
            "skew_detected": False,
            "skew_angle": None,
            "page_rectified": False,
            "special_handling": False,
        }
        if image is None or image.size == 0:
            raise ValueError("Anh dau vao khong hop le.")

        image = self._ensure_bgr(image)

        text_skew_angle = self._estimate_skew_angle(image)
        page_skew_angle = self._estimate_page_skew_angle(image)
        skew_angle = text_skew_angle
        if skew_angle is None or abs(skew_angle) < 1.2:
            skew_angle = page_skew_angle
        self.last_info["skew_angle"] = skew_angle
        self.last_info["skew_detected"] = bool(skew_angle is not None and abs(skew_angle) >= 1.2)

        image = self._resize_for_ocr(image)

        if self.mode == "resize":
            return image

        image = self._normalize_contrast(image)
        image = self._denoise_light(image)

        if self.mode in {"auto", "camera"} and self.last_info["skew_detected"]:
            rectified = self._rectify_document_page(image)
            if rectified.shape[:2] != image.shape[:2]:
                self.last_info["page_rectified"] = True
                image = rectified

        if self.mode in {"auto", "scan", "camera"} and self.last_info["skew_detected"]:
            image = self._deskew_light(image)

        if self.mode == "scan":
            image = self._binarize_for_scan(image)
        else:
            image = self._sharpen_light(image)

        self.last_info["special_handling"] = bool(
            self.last_info["skew_detected"] or self.last_info["page_rectified"]
        )
        return image

    def _read_image(self, file_path: str) -> np.ndarray:
        data = np.fromfile(file_path, dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Khong doc duoc anh: {file_path}")
        return image

    def _ensure_bgr(self, image: np.ndarray) -> np.ndarray:
        if len(image.shape) == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        if image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        return image

    def _resize_for_ocr(self, image: np.ndarray) -> np.ndarray:
        height, width = image.shape[:2]
        if width <= 0 or height <= 0:
            return image

        target_width = self.target_width
        if target_width is None:
            if width < self.min_width:
                target_width = self.min_width
            elif width > self.max_width:
                target_width = self.max_width
            else:
                return image

        scale = target_width / width
        target_height = max(1, int(height * scale))
        interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
        return cv2.resize(image, (target_width, target_height), interpolation=interpolation)

    def _normalize_contrast(self, image: np.ndarray) -> np.ndarray:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced_l = clahe.apply(l_channel)
        enhanced = cv2.merge((enhanced_l, a_channel, b_channel))
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    def _denoise_light(self, image: np.ndarray) -> np.ndarray:
        return cv2.bilateralFilter(image, d=5, sigmaColor=30, sigmaSpace=30)

    def _sharpen_light(self, image: np.ndarray) -> np.ndarray:
        blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=1.0)
        return cv2.addWeighted(image, 1.35, blurred, -0.35, 0)

    def _binarize_for_scan(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            9,
        )
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    def _rectify_document_page(self, image: np.ndarray) -> np.ndarray:
        source_points = self._find_document_quad(image)
        if source_points is None:
            return image

        ordered = self._order_points(source_points.astype("float32"))
        top_width = np.linalg.norm(ordered[1] - ordered[0])
        bottom_width = np.linalg.norm(ordered[2] - ordered[3])
        left_height = np.linalg.norm(ordered[3] - ordered[0])
        right_height = np.linalg.norm(ordered[2] - ordered[1])
        target_width = int(max(top_width, bottom_width))
        target_height = int(max(left_height, right_height))

        if target_width < 80 or target_height < 80:
            return image

        destination = np.array(
            [
                [0, 0],
                [target_width - 1, 0],
                [target_width - 1, target_height - 1],
                [0, target_height - 1],
            ],
            dtype="float32",
        )
        matrix = cv2.getPerspectiveTransform(ordered, destination)
        warped = cv2.warpPerspective(
            image,
            matrix,
            (target_width, target_height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return warped

    def _estimate_page_skew_angle(self, image: np.ndarray) -> float | None:
        source_points = self._find_document_quad(image)
        if source_points is None:
            return None

        ordered = self._order_points(source_points.astype("float32"))
        top_edge = ordered[1] - ordered[0]
        if np.linalg.norm(top_edge) < 30:
            return None
        angle = np.degrees(np.arctan2(top_edge[1], top_edge[0]))
        if abs(angle) > 25:
            return None
        return float(angle)

    def _find_document_quad(self, image: np.ndarray) -> np.ndarray | None:
        height, width = image.shape[:2]
        if height < 80 or width < 80:
            return None

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        bright_ratio = cv2.countNonZero(mask) / float(width * height)
        if bright_ratio < 0.08 or bright_ratio > 0.92:
            return None

        kernel_size = max(5, int(min(width, height) * 0.01))
        if kernel_size % 2 == 0:
            kernel_size += 1
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        contour = max(contours, key=cv2.contourArea)
        area_ratio = cv2.contourArea(contour) / float(width * height)
        if area_ratio < 0.18:
            return None

        return self._document_quad(contour)

    def _document_quad(self, contour: np.ndarray) -> np.ndarray | None:
        perimeter = cv2.arcLength(contour, True)
        for ratio in (0.015, 0.02, 0.03, 0.05):
            approx = cv2.approxPolyDP(contour, ratio * perimeter, True)
            if len(approx) == 4:
                return approx.reshape(4, 2)

        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)
        if box is None or len(box) != 4:
            return None
        return box

    def _order_points(self, points: np.ndarray) -> np.ndarray:
        rect = np.zeros((4, 2), dtype="float32")
        point_sum = points.sum(axis=1)
        rect[0] = points[np.argmin(point_sum)]
        rect[2] = points[np.argmax(point_sum)]

        point_diff = np.diff(points, axis=1)
        rect[1] = points[np.argmin(point_diff)]
        rect[3] = points[np.argmax(point_diff)]
        return rect

    def _deskew_light(self, image: np.ndarray) -> np.ndarray:
        angle = self._estimate_skew_angle(image)
        if angle is None or abs(angle) < 0.35 or abs(angle) > 8:
            return image

        height, width = image.shape[:2]
        center = (width / 2, height / 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(
            image,
            matrix,
            (width, height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    def _estimate_skew_angle(self, image: np.ndarray) -> float | None:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.bitwise_not(gray)
        _, threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        coords = np.column_stack(np.where(threshold > 0))
        if coords.shape[0] < 100:
            return None

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        return float(angle)
