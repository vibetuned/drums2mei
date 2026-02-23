import argparse
import json
import logging
from pathlib import Path
import cv2

from straighten import straighten_image, split_table
from row_index_ocr import extract_row_labels
from grid_parser import parse_grid
from pattern_num_ocr import extract_pattern_number
from merge_to_json import RAW_TO_CANONICAL

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def process_table_image(image_path: Path):
    """
    Runs the full extraction pipeline on a single raw table crop image.
    Returns the parsed pattern JSON dictionary if successful, or None if invalid.
    """
    # 1. Deskew the table
    straightened = straighten_image(image_path)
    if straightened is None:
        logging.error(f"Failed to straighten {image_path.name}")
        return None
        
    # We can fetch the memory matrices directly
    parts = split_table(straightened)
    if not parts:
        logging.error(f"Failed to split table for {image_path.name}")
        return None
        
    head, row_index, grid, pattern_num = parts
    
    logging.info(f"Extracting pattern number for {image_path.name}...")
    pattern_id = extract_pattern_number(pattern_num)
    
    if pattern_id is None:
        logging.warning("Could not identify pattern number. Skipping this table.")
        return None
        
    logging.info(f"Extracting row labels...")
    labels_data = extract_row_labels(row_index)
    labels = [label for _, label in labels_data]
    
    logging.info(f"Parsing grid hits...")
    grid_data = parse_grid(grid)
    
    if len(labels) != len(grid_data):
        logging.warning(f"Row count mismatch! Found {len(labels)} labels but {len(grid_data)} grid rows.")
        
    length = max(len(r) for r in grid_data if r) if grid_data else 16
    
    pattern_data = {
        "title": f"Pattern {pattern_id}",
        "signature": "4/4",
        "length": length,
        "tracks": {}
    }
    
    for label, row_hits in zip(labels, grid_data):
        canonical_inst = RAW_TO_CANONICAL.get(label, label.replace(" ", ""))
        steps = []
        for val in row_hits:
            if val == 'X':
                steps.append("Note")
            elif val == 'A':
                steps.append("Accent")
            else:
                steps.append("Rest")
                
        if canonical_inst in pattern_data["tracks"]:
            existing_steps = pattern_data["tracks"][canonical_inst]
            for i in range(min(length, len(steps))):
                if steps[i] != "Rest":
                    existing_steps[i] = steps[i]
        else:
            while len(steps) < length:
                steps.append("Rest")
            pattern_data["tracks"][canonical_inst] = steps
            
    return pattern_data

def main():
    parser = argparse.ArgumentParser(description="Process all grid images and combine into a single JSON.")
    parser.add_argument("-i", "--input-dir", type=str, default="output/parsed_grids_cv2", help="Input directory containing raw grid table images")
    parser.add_argument("-o", "--output", type=str, default="output/all_patterns.json", help="Path to final combined output JSON file")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_path = Path(args.output)
    
    if not input_dir.exists():
        logging.error(f"Input directory not found: {input_dir}")
        return
        
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    all_patterns = []
    
    image_files = sorted(input_dir.glob("*.png"))
    logging.info(f"Found {len(image_files)} image files to process in {input_dir}")
    
    for image_path in image_files:
        logging.info(f"--- Processing {image_path.name} ---")
        pattern_data = process_table_image(image_path)
        if pattern_data:
            all_patterns.append(pattern_data)
            
    # Write the master array to output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_patterns, f, indent=1)
        
    logging.info(f"Successfully processed {len(all_patterns)} patterns.")
    logging.info(f"Saved generated combined dataset to {output_path}")

if __name__ == "__main__":
    main()
