import argparse
import logging
from pathlib import Path

import cv2
import numpy as np
import pytesseract

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def cluster_coords(coords, threshold=10):
    if len(coords) == 0:
        return []
    clusters = []
    curr = [coords[0]]
    for c in coords[1:]:
        if c - curr[-1] < threshold:
            curr.append(c)
        else:
            clusters.append(int(np.mean(curr)))
            curr = [c]
    clusters.append(int(np.mean(curr)))
    return clusters


from typing import Union

def parse_grid(image_source: Union[Path, str, np.ndarray]):
    """
    Parses a 16-step grid image to find drum hits (X or A).
    Uses a virtual lattice by finding table boundaries, cutting it into 16 steps,
    and then verifying the fill ratio inside the cells.
    """
    if isinstance(image_source, np.ndarray):
        img = image_source
    else:
        img_path = str(image_source)
        img = cv2.imread(img_path)
        if img is None:
            logging.error(f"Failed to load image at {img_path}")
            return []

    if img is None or img.size == 0:
        logging.error("Parse grid received an empty image. Skipping.")
        return []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5
    )

    (h, w) = img.shape[:2]

    # Detect horizontal lines for rows
    # A kernel width of 50 is more robust against broken horizontal lines
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
    h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)
    h_sum = np.sum(h_lines, axis=1)
    y_peaks = np.where(h_sum > w * 255 * 0.4)[0]
    y_coords = cluster_coords(y_peaks)

    # Detect vertical lines. 
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 50))
    v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel)
    v_sum = np.sum(v_lines, axis=0)
    x_peaks = np.where(v_sum > h * 255 * 0.15)[0]
    x_coords = cluster_coords(x_peaks)

    logging.info(
        f"Detected {len(y_coords)-1} rows and {len(x_coords)-1} columns."
    )

    # Some images have a single measure (16 steps -> 17 lines) 
    # Some have two measures (32 steps -> 33 lines)
    if len(x_coords) > 10:
        cols = x_coords
    else:
        # Fallback if something failed catastrophically
        logging.info("Falling back to uniform 16-chunk spacing.")
        cols = np.linspace(0, w, 17, dtype=int)

    grid_data = []

    # Iterate row by row
    for i in range(len(y_coords) - 1):
        y1 = y_coords[i]
        y2 = y_coords[i + 1]
        row_h = y2 - y1

        if row_h < 10:
            continue

        row_vals = []
        num_cells = len(cols) - 1
        for j in range(num_cells):
            x1 = cols[j]
            x2 = cols[j + 1]
            cell_w = x2 - x1

            # Focus on the very center of the cell to ignore grid border bleeding
            pad_x = int(cell_w * 0.2)
            pad_y = int(row_h * 0.2)

            if cell_w > 2 * pad_x and row_h > 2 * pad_y:
                cell_roi = thresh[y1 + pad_y : y2 - pad_y, x1 + pad_x : x2 - pad_x]

                # A drum hit ("X") will heavily occupy the exact center of the cell
                fill_ratio = cv2.countNonZero(cell_roi) / (
                    cell_roi.shape[0] * cell_roi.shape[1] + 1e-6
                )

                if fill_ratio > 0.05:  # Over 5% filled in the inner core
                    # Let's use OCR strictly to differentiate X vs A (as user noted "A" exists)
                    ocr_img = cv2.bitwise_not(cell_roi)
                    kernel = np.ones((2, 2), np.uint8)
                    ocr_img = cv2.morphologyEx(ocr_img, cv2.MORPH_CLOSE, kernel)
                    
                    # Pad text with some white space to help Tesseract
                    ocr_img = cv2.copyMakeBorder(ocr_img, 5, 5, 5, 5, cv2.BORDER_CONSTANT, value=255)

                    text = pytesseract.image_to_string(
                        ocr_img, config='--psm 10 -c tessedit_char_whitelist=XA'
                    ).strip()

                    if "A" in text:
                        row_vals.append("A")
                    else:
                        row_vals.append("X")  # Default to X
                else:
                    row_vals.append("")
            else:
                row_vals.append("")

        grid_data.append(row_vals)
        logging.info(f"Row {i:02d}: {row_vals}")

    return grid_data


def main():
    parser = argparse.ArgumentParser(description="Parse 16 drum steps from a grid image.")
    parser.add_argument("input", type=str, help="Path to input grid image")
    args = parser.parse_args()

    input_path = Path(args.input)
    parse_grid(input_path)


if __name__ == "__main__":
    main()
