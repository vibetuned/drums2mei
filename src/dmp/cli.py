import argparse
import tempfile
import logging
from pathlib import Path
import json

from dmp.pdf.extract_cv2 import process_pdf
from dmp.image.straighten import straighten_image, split_table
from dmp.image.pattern_num_ocr import extract_pattern_number
from dmp.image.row_index_ocr import extract_row_labels
from dmp.image.grid_parser import parse_grid

# We need the canonical map directly imported from wherever it makes most sense. 
# Previously it was in merge_to_json, which we moved to legacy. Let's port the 
# mapping to this cli script directly or a dedicated mapping config file inside `exporters/`.
INSTRUMENT_MAP = {
    'BassDrum': ["Kick Bass"],
    'SnareDrum': ["Snare"],
    'LowTom': ["Tom 1"],
    'MediumTom': ["Tom 2"],
    'HighTom': ["Tom 3", "Tom 4"],
    'ClosedHiHat': ["Closed Hi-hat"],
    'OpenHiHat': ["Open Hi-hat", "1/4 Open Hi-hat", "Hi-hat pedal"],
    'Cymbal': ["Cymbal", "Crash", "China", "Ride (cup)", "Ride (edge)"],
}

RAW_TO_CANONICAL = {}
for canonical, raw_list in INSTRUMENT_MAP.items():
    for raw in raw_list:
        RAW_TO_CANONICAL[raw] = canonical

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def process_table_image(image_path: Path):
    """
    Runs the full extraction pipeline on a single raw table crop image.
    Returns the parsed pattern JSON dictionary if successful, or None if invalid.
    """
    straightened = straighten_image(image_path)
    if straightened is None:
        logging.error(f"Failed to straighten {image_path.name}")
        return None
        
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
        
    logging.info(f"Extracting row labels for pattern {pattern_id}...")
    labels_data = extract_row_labels(row_index)
    labels = [label for _, label in labels_data]
    
    logging.info(f"Parsing grid hits for pattern {pattern_id}...")
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

def process_pdf_to_json(pdf_path: Path, output_json: Path):
    """
    Unified pipeline: PDF -> Table Crops (temp dir) -> JSON array mapping.
    """
    output_json.parent.mkdir(parents=True, exist_ok=True)
    all_patterns = []
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        logging.info(f"Extracting PDF tables into temporary directory: {temp_path}")
        
        # 1. Extract CV2 table crops from PDF into the temporary directory
        process_pdf(pdf_path, temp_path)
        
        image_files = sorted(temp_path.glob("*.png"))
        logging.info(f"Found {len(image_files)} table crop images to process.")
        
        # 2. Process each cropped image through the orchestrator sequence
        for image_path in image_files:
            logging.info(f"--- Processing {image_path.name} ---")
            pattern_data = process_table_image(image_path)
            if pattern_data:
                all_patterns.append(pattern_data)
                
    # 3. Save the resulting master array
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_patterns, f, indent=1)
        
    logging.info(f"Successfully processed {len(all_patterns)} patterns.")
    logging.info(f"Saved generated dataset to {output_json}")

def main():
    parser = argparse.ArgumentParser(description="Unified pipeline: Extract drum patterns directly from a PDF and output to JSON.")
    parser.add_argument("pdf_path", type=str, help="Path to input PDF file containing drum pattern tables")
    parser.add_argument("-o", "--output", type=str, default="output/all_patterns.json", help="Path to output JSON file")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    output_path = Path(args.output)
    
    if not pdf_path.exists():
        logging.error(f"Input PDF not found: {pdf_path}")
        return
        
    process_pdf_to_json(pdf_path, output_path)

if __name__ == "__main__":
    main()
