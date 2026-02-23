import argparse
from pathlib import Path
import cv2
import numpy as np

def deskew_and_parse(image_path: Path, output_dir: Path):
    img = cv2.imread(str(image_path))
    if img is None:
        return
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Adaptive thresholding to handle lighting
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5)
    
    # 1. DESKEW
    # Find all coordinates of foreground (white) pixels
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) == 0:
        return # Empty image
        
    # Get the bounding box of minimum area (capable of rotating)
    angle = cv2.minAreaRect(coords)[-1]
    
    # minAreaRect returns angles in range [-90, 0)
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
        
    # Only deskew if the angle is significant but not exactly 90 degrees
    # If the angle is very large, it means minAreaRect miscalculated the dominant orientation of a landscape table
    if abs(angle) > 0.1 and abs(angle) < 45:
        (h, w) = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        # Calculate new bounding dimensions
        cos_val = np.abs(M[0, 0])
        sin_val = np.abs(M[0, 1])
        nW = int((h * sin_val) + (w * cos_val))
        nH = int((h * cos_val) + (w * sin_val))
        M[0, 2] += (nW / 2) - center[0]
        M[1, 2] += (nH / 2) - center[1]
        
        # Warp the image to deskew it, padding with white
        img = cv2.warpAffine(img, M, (nW, nH), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
        
        # Re-threshold the newly rotated image
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5)
        
    # 2. GRID VALIDATION
    # Detect horizontal lines
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
    detect_horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    
    # Detect vertical lines
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 50))
    detect_vertical = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel, iterations=1)
    
    # Find intersections (where horizontal and vertical lines cross)
    intersections = cv2.bitwise_and(detect_horizontal, detect_vertical)
    
    # Count the number of intersection points
    # A genuine tabular grid will have dozens of intersections (rows * cols)
    # A block of text or a false positive header will usually have < 5
    _, intersection_labels, stats, _ = cv2.connectedComponentsWithStats(intersections, connectivity=8)
    
    # The first component is the background, so true intersections = len(stats) - 1
    num_intersections = len(stats) - 1
    
    # Drum patterns are roughly 17 columns (16 steps + instrument name) and ~5+ rows
    # We should expect at least 30-40 intersections for a valid drum pattern
    if num_intersections > 20:
        # It's a valid grid! Save the deskewed version
        output_path = output_dir / image_path.name
        cv2.imwrite(str(output_path), img)
        print(f"✅ Valid Grid Confirmed (Intersections: {num_intersections}): Deskewed and saved {image_path.name}")
    else:
        print(f"❌ False Positive (Intersections: {num_intersections}): Skipped {image_path.name}")


def main():
    parser = argparse.ArgumentParser(description="Deskew and validate drum pattern grids")
    parser.add_argument("input_dir", type=str, help="Directory containing the OpenCV bounded images")
    parser.add_argument("--output-dir", type=str, default=".", help="Directory to save the validated grids")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    
    if not input_dir.exists():
        print(f"Error: Directory not found - {input_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    
    image_paths = sorted([p for p in input_dir.iterdir() if p.suffix.lower() == '.png'])
    print(f"Found {len(image_paths)} images to parse. Validating grids...")
    
    for p in image_paths:
        deskew_and_parse(p, output_dir)


if __name__ == "__main__":
    main()
