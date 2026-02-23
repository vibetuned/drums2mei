import argparse
import logging
from pathlib import Path
import re

import cv2
import numpy as np
import pytesseract

from typing import Union

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def extract_pattern_number(image_source: Union[Path, np.ndarray]):
    """
    Extracts the pattern number (usually 0-50, or up to 200 in the book) 
    from the cell containing the pattern title.
    Returns the number if found, or None if it appears to be a false positive grid.
    """
    if isinstance(image_source, Path) or isinstance(image_source, str):
        img = cv2.imread(str(image_source))
        if img is None:
            logging.error(f"Failed to load image at {image_source}")
            return None
        image_name = Path(image_source).name
    else:
        img = image_source
        image_name = "memory_image"

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Simple thresholding since this is typically clean text on a plain background
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Slight dilation to connect broken features
    kernel = np.ones((2, 2), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    # Invert for Tesseract (black text on white background)
    ocr_img = cv2.bitwise_not(thresh)
    
    # Pad to help OCR
    ocr_img = cv2.copyMakeBorder(ocr_img, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)

    # Force Tesseract to parse numbers
    # Whitelisting digits helps, but sometimes "O" and "I" still sneak through if the font is weird
    custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789'
    
    text = pytesseract.image_to_string(ocr_img, config=custom_config).strip()
    
    # If the whitelist failed, try a manual fix for common letter/number confusions
    if not text:
        text = pytesseract.image_to_string(ocr_img, config=r'--oem 3 --psm 6').strip()
        text = text.replace('O', '0').replace('o', '0').replace('I', '1').replace('l', '1').replace('S', '5')
        
    logging.info(f"Raw OCR output from {image_name}: {repr(text)}")
    
    # Extract the first contiguous number block
    numbers = re.findall(r'\d+', text)
    
    if numbers:
        # Assuming the largest apparent number is likely the pattern ID 
        # (in case there are other stray '1's or noise)
        valid_nums = [int(n) for n in numbers if 1 <= int(n) <= 200]
        
        if valid_nums:
            pattern_id = max(valid_nums)
            logging.info(f"Successfully identified Pattern ID: {pattern_id}")
            return pattern_id
            
    logging.warning("No valid pattern number found. This might be a false positive grid.")
    return None


def main():
    parser = argparse.ArgumentParser(description="Extract pattern ID from the top-left cell.")
    parser.add_argument("input", type=str, help="Path to input pattern number crop")
    args = parser.parse_args()

    input_path = Path(args.input)
    extract_pattern_number(input_path)


if __name__ == "__main__":
    main()
