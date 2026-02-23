import argparse
from pathlib import Path
import fitz
import cv2
import numpy as np
from PIL import Image

def process_pdf(pdf_path: Path, output_dir: Path):
    doc = fitz.open(pdf_path)
    table_idx = 1
    
    print(f"Processing: {pdf_path} (OpenCV logic)...")

    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Render page at 300 DPI
        zoom = 300 / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert PyMuPDF pixmap to numpy array (RGB -> BGR for OpenCV)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply Adaptive Thresholding instead of CLAHE and Otsu
        # This handles shadows gracefully by checking local regions
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5)
        
        # Detect horizontal lines (kernel size 40 to strictly catch long lines, avoiding text)
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        detect_horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
        
        # Detect vertical lines (kernel size 40)
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        detect_vertical = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel, iterations=1)
        
        # Combine
        table_mask = cv2.add(detect_horizontal, detect_vertical)
        
        # Group lines to form a solid table block
        # Use a smaller kernel so we only connect actual intersecting lines, not surrounding noise
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (10, 10))
        connected = cv2.morphologyEx(table_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        # Find contours
        contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Filter contours by size to find tables
        bounding_boxes = []
        page_h, page_w = img.shape[:2]
        
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            # Relaxed boundaries: Tables must be at least 200px wide and 50px tall
            # They also must not span 95% of the page (which indicates the page border was mistakenly grabbed)
            if w > 200 and h > 50 and h < (page_h * 0.95):
                # Optionally filter false positive long thin lines: Ensure aspect ratio is reasonable
                # If width is extremely disproportionate to height (like w=1000, h=52), it might be a single line.
                # Since drum grids have multiple rows, h usually > 100 for a grid. Let's keep h>50 just in case.
                bounding_boxes.append((x, y, w, h))
        
        # Sort top to bottom
        bounding_boxes = sorted(bounding_boxes, key=lambda b: b[1])
        
        for x, y, w, h in bounding_boxes:
            # Add a small padding
            pad = 10
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(img.shape[1], x + w + pad)
            y2 = min(img.shape[0], y + h + pad)
            
            cropped = img[y1:y2, x1:x2]
            
            # Save cropped image
            image_path = output_dir / f"{pdf_path.stem}_table_{table_idx}.png"
            cv2.imwrite(str(image_path), cropped)
            print(f"✅ Saved CV2 cropped Table {table_idx} image to {image_path}")
            
            table_idx += 1


def main():
    parser = argparse.ArgumentParser(description="Extract tables using pure OpenCV contours")
    parser.add_argument("pdf_path", type=str, help="Path to the PDF file")
    parser.add_argument("--output-dir", type=str, default=".", help="Directory to save the extracted images")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    output_dir = Path(args.output_dir)
    
    if not pdf_path.exists():
        print(f"Error: File not found - {pdf_path}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    process_pdf(pdf_path, output_dir)

if __name__ == "__main__":
    main()
