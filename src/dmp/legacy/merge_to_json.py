import argparse
import json
import logging
from pathlib import Path

from row_index_ocr import extract_row_labels
from grid_parser import parse_grid
from pattern_num_ocr import extract_pattern_number

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

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

def generate_pattern_json(row_idx_path: Path, grid_path: Path, pattern_num_path: Path, output_dir: Path):
    """
    Parses the three image components and builds the final JSON structure directly.
    """
    logging.info(f"Extracting pattern number from {pattern_num_path}...")
    pattern_id = extract_pattern_number(pattern_num_path)
    
    if pattern_id is None:
        logging.warning("Could not identify pattern number. Skipping this table.")
        return
        
    logging.info(f"Extracting row labels from {row_idx_path}...")
    labels_data = extract_row_labels(row_idx_path)
    labels = [label for _, label in labels_data]
    
    logging.info(f"Parsing grid hits from {grid_path}...")
    grid_data = parse_grid(grid_path)
    
    if len(labels) != len(grid_data):
        logging.warning(f"Row count mismatch! Found {len(labels)} labels but {len(grid_data)} grid rows.")
        
    # Grid length is governed by the length of the cell arrays
    length = max(len(r) for r in grid_data if r) if grid_data else 16
    
    pattern_data = {
        "title": f"Pattern {pattern_id}",
        "signature": "4/4",
        "length": length,
        "tracks": {}
    }
    
    for label, row_hits in zip(labels, grid_data):
        # Map instrument name
        canonical_inst = RAW_TO_CANONICAL.get(label, label.replace(" ", ""))
        
        # Convert X/A to Note/Accent/Rest
        steps = []
        for val in row_hits:
            if val == 'X':
                steps.append("Note")
            elif val == 'A':
                steps.append("Accent")
            else:
                steps.append("Rest")
                
        # Merge identical mapped instruments
        if canonical_inst in pattern_data["tracks"]:
            existing_steps = pattern_data["tracks"][canonical_inst]
            for i in range(min(length, len(steps))):
                if steps[i] != "Rest":
                    existing_steps[i] = steps[i]
        else:
            # Pad just in case there was a length discrepancy
            while len(steps) < length:
                steps.append("Rest")
            pattern_data["tracks"][canonical_inst] = steps
            
    out_file = output_dir / f"pattern_{pattern_id}.json"
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(pattern_data, f, indent=1)
        
    logging.info(f"Successfully wrote JSON to {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Merge extracted components directly to JSON")
    parser.add_argument("row_idx", type=str, help="Path to test_row_idx.png")
    parser.add_argument("grid", type=str, help="Path to test_grid.png")
    parser.add_argument("pattern_num", type=str, help="Path to test_pattern_num.png")
    parser.add_argument("-o", "--output-dir", type=str, default="output", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    generate_pattern_json(Path(args.row_idx), Path(args.grid), Path(args.pattern_num), out_dir)


if __name__ == "__main__":
    main()
