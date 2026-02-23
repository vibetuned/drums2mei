import argparse
import logging
from pathlib import Path

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def straighten_image(image_path: Path, output_path: Path = None):
    """
    Reads an image, determines its skew angle using isolated horizontal lines,
    rotates it to be exactly horizontal, and saves the result if output is provided.
    Returns the straightened Numpy array.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        logging.error(f"Failed to load image at {image_path}")
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Adaptive threshold to isolate grid lines
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5)
    
    # Isolate horizontal lines to make the variance score sharper
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
    detect_horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    
    # We will test angles from -5.0 to +5.0 degrees
    # If the image is already straight, 0.0 will have the highest variance
    angles_to_test = np.arange(-5.0, 5.1, 0.1)
    
    best_angle = 0.0
    max_variance = 0.0
    
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    
    for angle in angles_to_test:
        # Rotate the horizontal lines image
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated_lines = cv2.warpAffine(detect_horizontal, M, (w, h), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        
        # Project horizontally (sum across the width)
        projection = np.sum(rotated_lines, axis=1)
        
        # Calculate variance of the projection
        # When lines are perfectly horizontal, the projection will have sharp peaks and deep valleys -> high variance
        variance = np.var(projection)
        
        if variance > max_variance:
            max_variance = variance
            best_angle = angle
            
    logging.info(f"Detected optimal skew angle via projection profile: {best_angle:.2f} degrees")
    
    # Now we know the angle that makes it straight.
    # The image is tilted by `-best_angle`, so rotating by `best_angle` straightens it!
    median_angle = best_angle
    
    if abs(median_angle) < 0.05:
        logging.info("Image is straight enough. No rotation needed.")
        if output_path:
            cv2.imwrite(str(output_path), img)
        return img
    
    logging.info(f"Detected skew angle: {median_angle:.3f} degrees")
    
    # We want to rotate to make the angle 0.
    # getRotationMatrix2D rotates anti-clockwise for positive angle.
    # Our angle represents the current tilt. To fix it, we need to rotate by the same amount.
    rotation_angle = median_angle
    
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, rotation_angle, 1.0)
    
    # Calculate new bounding dimensions
    cos_val = np.abs(M[0, 0])
    sin_val = np.abs(M[0, 1])
    nW = int((h * sin_val) + (w * cos_val))
    nH = int((h * cos_val) + (w * sin_val))
    M[0, 2] += (nW / 2) - center[0]
    M[1, 2] += (nH / 2) - center[1]
    
    # Warping the image with white background
    rotated = cv2.warpAffine(img, M, (nW, nH), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    
    if output_path:
        cv2.imwrite(str(output_path), rotated)
        logging.info(f"Saved straightened image to {output_path}")
        
    return rotated
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

def split_table(image_source: Union[Path, str, np.ndarray]):
    """
    Finds the grid lines and splits the image into head, row_index, and grid.
    Returns the individual parts as numpy arrays.
    """
    if isinstance(image_source, Path) or isinstance(image_source, str):
        img_path = str(image_source)
        img = cv2.imread(img_path)
        if img is None:
            logging.error(f"Failed to load image at {img_path} for splitting")
            return None
    else:
        img = image_source

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5)
    
    (h, w) = img.shape[:2]
    
    # Horizontal lines
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 10, 1))
    h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)
    
    # Vertical lines
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h // 10))
    v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel)
    
    h_sum = np.sum(h_lines, axis=1) # Sum across columns
    v_sum = np.sum(v_lines, axis=0) # Sum across rows
    
    # A line must span at least a significant portion of the image to be considered a major grid line
    y_peaks = np.where(h_sum > w * 255 * 0.4)[0]
    x_peaks = np.where(v_sum > h * 255 * 0.15)[0] # 15% for vertical lines
    
    y_coords = cluster_coords(y_peaks)
    x_coords = cluster_coords(x_peaks)
    
    logging.info(f"Found {len(x_coords)} vertical lines and {len(y_coords)} horizontal lines.")
    
    if len(x_coords) < 3 or len(y_coords) < 4:
        logging.error("Could not find enough grid lines to split the table.")
        return
        
    # The top-left corner of the entire table is bounded by the first vertical and horizontal lines
    table_left = x_coords[0]
    table_right = x_coords[-1]
    table_top = y_coords[0]
    table_bottom = y_coords[-1]
    table_area = (table_right - table_left) * (table_bottom - table_top)
    
    # Find the empty square in the top-left that shares this starting coordinate
    grid_mask = cv2.bitwise_or(h_lines, v_lines)
    kernel = np.ones((3,3), np.uint8)
    grid_mask = cv2.dilate(grid_mask, kernel, iterations=1)
    cells = cv2.bitwise_not(grid_mask)
    
    contours, _ = cv2.findContours(cells, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    
    best_box = None
    max_area = 0
    
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        area = bw * bh
        
        # Must be inside the table slightly (allow small tolerance)
        if x < table_left - 15 or y < table_top - 15:
            continue
        
        # The cell MUST actually start at the top-left of the table!
        # Give it a 20-pixel tolerance for mask bleeding
        if abs(x - table_left) < 30 and abs(y - table_top) < 30:
            if area > max_area and area < table_area * 0.4:  # Avoid matching the entire table
                max_area = area
                best_box = (x, y, bw, bh)
                
    if best_box is None:
        logging.error(f"Could not find the top-left cell starting near {table_left}, {table_top} to determine split boundaries.")
        return
        
    bx, by, bw, bh = best_box
    logging.info(f"Top-left origin cell found at x={bx} y={by} w={bw} h={bh}")
    
    # Snap the right/bottom edge of this cell to the closest detected grid lines
    grid_start_x = min(x_coords, key=lambda cx: abs(cx - (bx + bw)))
    head_end_y = min(y_coords, key=lambda cy: abs(cy - (by + bh)))
    
    right_x = x_coords[-1]
    bottom_y = y_coords[-1]
    
    head = img[table_top:head_end_y, table_left:table_right]
    
    # If the left edge of the head starts before the grid (e.g. over the instrument names)
    # the user specifically asked: "the row index the left most part... keep row index and grid at hand"
    row_index = img[head_end_y:table_bottom, table_left:grid_start_x]
    grid = img[head_end_y:table_bottom, grid_start_x:table_right]
    
    # Extract the top-left rectangle containing the pattern number
    pattern_num = img[by:by+bh, bx:bx+bw]
    
    return head, row_index, grid, pattern_num

def main():
    parser = argparse.ArgumentParser(description="Straighten and split a drum pattern image.")
    parser.add_argument("input", type=str, help="Path to input image")
    parser.add_argument("-o", "--output", type=str, default="test_straightened.png", help="Path to output image")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logging.error(f"Input file not found: {input_path}")
        return

    straightened = straighten_image(input_path, Path(args.output))
    if straightened is not None:
        parts = split_table(input_path, straightened)
        if parts:
            head, row_index, grid, pattern_num = parts
            
            # Save the parts directly here to preserve its standalone function
            out_dir = input_path.parent
            cv2.imwrite(str(out_dir / "test_head.png"), head)
            cv2.imwrite(str(out_dir / "test_row_idx.png"), row_index)
            cv2.imwrite(str(out_dir / "test_grid.png"), grid)
            cv2.imwrite(str(out_dir / "test_pattern_num.png"), pattern_num)
            
            logging.info(f"Saved test_head.png, test_row_idx.png, test_grid.png, and test_pattern_num.png to {out_dir}")

if __name__ == "__main__":
    main()
