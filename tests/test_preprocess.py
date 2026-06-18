import os
import tempfile

import cv2
import numpy as np

from src.preprocess import ImagePreprocessor


def test_preprocessor_creates_ocr_ready_temp_image():
    image = np.full((200, 320, 3), 255, dtype=np.uint8)
    cv2.putText(image, "Invoice 123", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    fd, input_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        cv2.imwrite(input_path, image)
        preprocessor = ImagePreprocessor(mode="auto", min_width=640, max_width=1000)

        output_path = preprocessor.preprocess_to_temp_file(input_path)
        try:
            processed = cv2.imread(output_path)
            assert processed is not None
            assert processed.shape[1] == 640
            assert processed.shape[0] > image.shape[0]
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)


def test_preprocessor_can_be_disabled():
    preprocessor = ImagePreprocessor(mode="none")

    assert not preprocessor.should_preprocess("document.png")


def test_preprocessor_rectifies_bright_page_on_dark_background():
    image = np.zeros((360, 520, 3), dtype=np.uint8)
    page_box = cv2.boxPoints(((260, 180), (380, 190), -8))
    page_box = page_box.astype(np.int32)
    cv2.fillConvexPoly(image, page_box, (255, 255, 255))
    cv2.putText(image, "OCR sample", (135, 175), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    preprocessor = ImagePreprocessor(mode="auto", min_width=200, max_width=900)
    processed = preprocessor.preprocess_array(image)

    assert processed.shape[1] > processed.shape[0]
    assert processed.shape[0] < image.shape[0] * 0.85
    assert processed.mean() > 160
