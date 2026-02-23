import argparse
from pathlib import Path
import cv2
import numpy as np
import pytesseract
import csv

def process_grid(image_path: Path, output_file: Path):
    img = cv2.imread(str(image_path))
    if img is None:
        return
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5)
    
    # 1. Detect Grid Lines
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
    detect_horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 50))
    detect_vertical = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel, iterations=1)
    
    # Instead of findContours on cells (which is unreliable), we find the coordinates of the lines themselves
    
    # Get Y coordinates of all horizontal lines
    # Sum the horizontal lines mask across the X axis. Peaks will be the Y locations of lines
    (h, w) = img.shape[:2]
    horizontal_sum = np.sum(detect_horizontal, axis=1)
    y_lines = np.where(horizontal_sum > w * 0.5 * 255)[0] # Line must span at least 50% of width
    
    # Cluster Y lines that are close together (thickness of the line)
    y_coords = []
    if len(y_lines) > 0:
        current_cluster = [y_lines[0]]
        for y in y_lines[1:]:
            if y - current_cluster[-1] < 10: # Lines within 10 pixels are the same grid line
                current_cluster.append(y)
            else:
                y_coords.append(int(np.mean(current_cluster)))
                current_cluster = [y]
        y_coords.append(int(np.mean(current_cluster)))
        
    # Get X coordinates of all vertical lines
    # Sum the vertical lines mask across the Y axis. Peaks will be the X locations of lines
    vertical_sum = np.sum(detect_vertical, axis=0)
    x_lines = np.where(vertical_sum > h * 0.2 * 255)[0] # Vertical lines can be shorter, e.g., 20% of height
    
    # Cluster X lines
    x_coords = []
    if len(x_lines) > 0:
        current_cluster = [x_lines[0]]
        for x in x_lines[1:]:
            if x - current_cluster[-1] < 10:
                current_cluster.append(x)
            else:
                x_coords.append(int(np.mean(current_cluster)))
                current_cluster = [x]
        x_coords.append(int(np.mean(current_cluster)))
        
    # Validate the grid: we expect ~17 vertical lines (16 spaces + instrument name space + borders)
    # So we should have around 18 X coordinates.
    # And we expect at least 3-4 horizontal lines (rows).
    if len(x_coords) < 10 or len(y_coords) < 4:
        print(f"⚠️ Not enough grid lines found in {image_path.name}")
        return
        
    # The instrument name column is the first cell, which is often wider.
    # Sometimes there isn't a left border, so the first cell might be from x=0 to x_coords[0].
    # Generally the steps are neatly in the last 16 columns.
    
    # Since some grids are tricky and might have extra vertical lines on the left for the instrument section,
    # we'll grab the LAST 16 columns as the steps.
    if len(x_coords) > 16:
        step_x_coords = x_coords[-17:]
    else:
        step_x_coords = x_coords
        
    table_data = []
    
    # Iterate over the rows top to bottom
    for i in range(len(y_coords) - 1):
        y1_top = y_coords[i]
        y2_bottom = y_coords[i+1]
        
        row_h = y2_bottom - y1_top
        if row_h < 15: # Ignore tiny rows (noise)
            continue
            
        row_data = []
        
        # 1. OCR the instrument name
        inst_x1 = 0
        inst_x2 = step_x_coords[0]
        
        # Crop inward by a few pixels to avoid catching the grid lines which Tesseract reads as "I" or "l"
        pad_inst = 4
        if inst_x2 - inst_x1 > pad_inst * 2 and y2_bottom - y1_top > pad_inst * 2:
            inst_roi = gray[y1_top+pad_inst:y2_bottom-pad_inst, inst_x1+pad_inst:inst_x2-pad_inst]
        else:
            inst_roi = gray[y1_top:y2_bottom, inst_x1:inst_x2]
        # We need to test if there's actually text here, or if this is an empty margin
        _, inst_thresh = cv2.threshold(inst_roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Connect broken text lines and remove tiny specs
        text_kernel = np.ones((1, 2), np.uint8)
        inst_thresh_clean = cv2.morphologyEx(inst_thresh, cv2.MORPH_CLOSE, text_kernel)
        inst_thresh_clean = cv2.morphologyEx(inst_thresh_clean, cv2.MORPH_OPEN, text_kernel)
        
        # Binarize the text to black on white background so Tesseract can read it clearly
        ocr_img = cv2.bitwise_not(inst_thresh_clean)
        
        inst_fill = cv2.countNonZero(inst_thresh) / (inst_roi.shape[0] * inst_roi.shape[1] + 1)
        
        if inst_fill > 0.02 and inst_x2 - inst_x1 > 30: 
            # Force Tesseract to only read standard alphanumeric characters and common symbols
            whitelist = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/()-"
            raw_text = pytesseract.image_to_string(ocr_img, config=f'--psm 7 -c tessedit_char_whitelist={whitelist}').strip()
            
            # Fuzzy match to known instruments or header labels
            KNOWN_INSTRUMENTS = [
                "Cymbal", "Tom 4", "Tom 3", "Kick Bass", "Tom 2", "Snare", "Tom 1", 
                "Hi-hat pedal", "Open Hi-hat", "Closed Hi-hat", "1/4 Open Hi-hat", 
                "Ride (cup)", "Ride (edge)", "Crash", "China",
                "1st Measure", "2nd Measure", "1", "2", "3", "4", "5", "6", "7", "8", "9", 
                "10", "11", "12", "13", "14", "15", "16"
            ]
            
            if len(raw_text) >= 1:
                from thefuzz import process
                best_match, score = process.extractOne(raw_text, KNOWN_INSTRUMENTS)
                # If it's a reasonably close match, use the standard name
                if score >= 40:
                    text = best_match
                else:
                    text = f"Inst_Row_{i}"
            else:
                text = f"Inst_Row_{i}"
        else:
            text = f"Inst_Row_{i}"
            
        row_data.append(text)
        
        # 2. Extract the 16 steps
        for j in range(len(step_x_coords) - 1):
            x1_left = step_x_coords[j]
            x2_right = step_x_coords[j+1]
            
            cell_w = x2_right - x1_left
            if cell_w < 5:
                continue
                
            # Focus on the EXACT center of the cell to ignore thick borders and noise
            # A 35% padding means we only look at the middle 30% of the box
            pad_x = int(cell_w * 0.35)
            pad_y = int(row_h * 0.35)
            
            if cell_w > 2 * pad_x and row_h > 2 * pad_y:
                center_roi = gray[y1_top+pad_y:y2_bottom-pad_y, x1_left+pad_x:x2_right-pad_x]
                _, cell_thresh = cv2.threshold(center_roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                
                kernel = np.ones((2,2), np.uint8)
                cell_thresh = cv2.morphologyEx(cell_thresh, cv2.MORPH_OPEN, kernel, iterations=1)
                
                filled_ratio = cv2.countNonZero(cell_thresh) / (center_roi.shape[0] * center_roi.shape[1] + 1)
                
                # A drum dot perfectly centered in this padded ROI will take up a significant amount of the tiny remaining box (often > 20%)
                if filled_ratio > 0.15: 
                    row_data.append("X")
                else:
                    row_data.append("")
            else:
                 row_data.append("")
                 
        # Additional debug filter: if the row is literally all X's, the hit threshold is miscalibrated for this image, or it's a solid black header row
        if row_data[1:].count("X") > 14:
            continue
            
        # If the string match failed completely, and there are basically no dots in the row, it's just noise lines on the page.
        if row_data[0].startswith("Inst_Row_") and row_data[1:].count("X") < 2:
            continue
            
        table_data.append(row_data)
        
    # Write to CSV
    if table_data:
        file_exists = output_file.exists()
        with open(output_file, 'a', newline='') as csvfile:
            writer = cv2.csv.writer(csvfile) if hasattr(cv2, 'csv') else csv.writer(csvfile)
            if file_exists:
                writer.writerow([])
            writer.writerow([f"--- Drum Pattern from {image_path.name} ---"])
            for row in table_data:
                # Basic filter: if row doesn't have at least one drum hit AND didn't recognize any text, it's probably the empty table header row
                hits = row[1:].count("X")
                if hits > 0 or not row[0].startswith("Inst_Row_"):
                    writer.writerow(row)
        print(f"✅ Extracted data from {image_path.name}")
    else:
        print(f"⚠️ No tabular data found in {image_path.name}")

def main():
    parser = argparse.ArgumentParser(description="Extract grid data from parsed images")
    parser.add_argument("input_dir", type=str, help="Directory containing the parsed grid images")
    parser.add_argument("--output-csv", type=str, default="drum_patterns_raw.csv", help="Output combined CSV file")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_csv = Path(args.output_csv)
    
    if not input_dir.exists():
        print(f"Error: Directory not found - {input_dir}")
        return
        
    # Clear the output CSV if it exists
    if output_csv.exists():
        output_csv.unlink()
    
    image_paths = sorted([p for p in input_dir.iterdir() if p.suffix.lower() == '.png'])
    print(f"Found {len(image_paths)} images to process. Extracting data...")
    
    for p in image_paths:
        process_grid(p, output_csv)

if __name__ == "__main__":
    main()
