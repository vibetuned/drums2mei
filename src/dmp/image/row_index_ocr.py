import argparse
import logging
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from thefuzz import process

from typing import List, Tuple, Union

# --- Configuration ---
KNOWN_INSTRUMENTS = [
    "Cymbal", "Tom 4", "Tom 3", "Kick Bass", "Tom 2", "Snare", "Tom 1", 
    "Hi-hat pedal", "Open Hi-hat", "Closed Hi-hat", "1/4 Open Hi-hat", 
    "Ride (cup)", "Ride (edge)", "Crash", "China"
]

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

def extract_row_labels(image_source: Union[Path, str, np.ndarray]) -> List[Tuple[int, str]]:
    """
    Extracts the instrument names from the row index image.
    Uses horizontal lines to split the rows, then Tesseract to read the text.
    Fuzzy matches against KNOWN_INSTRUMENTS to ensure validity.
    """
    if isinstance(image_source, Path) or isinstance(image_source, str):
        img_path = str(image_source)
        img = cv2.imread(img_path)
        if img is None:
            logging.error(f"Failed to load image at {img_path}")
            return []
    else:
        img = image_source

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5)
    
    (h, w) = img.shape[:2]
    
    # Detect horizontal lines to find the rows
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 2, 1))
    h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)
    
    h_sum = np.sum(h_lines, axis=1)
    y_peaks = np.where(h_sum > w * 255 * 0.5)[0]
    
    y_coords = cluster_coords(y_peaks)
    
    # Always include top and bottom boundaries even if lines aren't fully perfectly detected
    if y_coords[0] > 10:
        y_coords.insert(0, 0)
    if h - y_coords[-1] > 10:
        y_coords.append(h)
        
    logging.info(f"Found {len(y_coords)-1} rows.")
    
    results = []
    
    # Iterate through the rows
    for i in range(len(y_coords) - 1):
        y1 = y_coords[i]
        y2 = y_coords[i+1]
        
        row_h = y2 - y1
        if row_h < 10:  # Ignore tiny slivers
            continue
            
        # Add padding inward to avoid capturing the border lines which Tesseract misinterprets
        pad = max(2, int(row_h * 0.1))
        if row_h > 2 * pad:
            roi_gray = gray[y1+pad:y2-pad, :]
            
            # Simple thresholding for Tesseract
            _, roi_thresh = cv2.threshold(roi_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # Remove specs and connect letters slightly
            kernel = np.ones((2, 2), np.uint8)
            roi_clean = cv2.morphologyEx(roi_thresh, cv2.MORPH_CLOSE, kernel)
            
            # Invert back to black text on white background
            ocr_img = cv2.bitwise_not(roi_clean)
            
            # Force Tesseract to read standard alphabet
            whitelist = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/()-"
            raw_text = pytesseract.image_to_string(ocr_img, config=f'--psm 7 -c tessedit_char_whitelist={whitelist}').strip()
            
            if len(raw_text) > 1:
                best_match, score = process.extractOne(raw_text, KNOWN_INSTRUMENTS)
                
                # If score is somewhat decent, take it
                if score >= 40:
                    text_result = best_match
                else:
                    text_result = f"Unknown: {raw_text}"
            else:
                text_result = f"EmptyRow_{i}"
                
            results.append((y1, text_result))
            logging.info(f"Row {i:02d} (y={y1}): {raw_text:<20} -> {text_result}")
            
    return results

def main():
    parser = argparse.ArgumentParser(description="Extract row labels from a row index image.")
    parser.add_argument("input", type=str, help="Path to input row index image")
    args = parser.parse_args()

    input_path = Path(args.input)
    extract_row_labels(input_path)

if __name__ == "__main__":
    main()
