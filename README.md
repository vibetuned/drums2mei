# Drum Midi Pattern (DMP) Extractor

DMP is an end-to-end Python pipeline designed to extract rhythmic drum patterns directly from raw scanned PDF tables, convert them into a structured JSON array, and instantly export them as standard MEI (Music Encoding Initiative) percussion sheets.

## Overview

The optical drum extraction pipeline uses OpenCV and PyTesseract for highly effective structural extraction and reading of rhythmic notation arrays:

1. **Table Extraction** (`src/dmp/pdf/extract_cv2.py`): Parses through raw PDF blocks, recognizes visual bounds using adaptive thresholding, and exports strictly cropped table subsets into high-quality OpenCV arrays.
2. **Image Rotation and Alignment** (`src/dmp/image/straighten.py`): Performs analytical histogram rotation of table cells to ensure perfect alignment prior to OCR chunking.
3. **Data Splitting** (`src/dmp/image/`): Modularly isolates grids, table headers, and numerical instrument rows, independently parsing hit thresholds (e.g. `X` or `A`) into discrete values.
4. **JSON Dataset** (`src/dmp/cli.py`): Fuses all 3 modules into `parse` sequentially, dynamically piping the PDF image stream through the parser and exporting 100% canonized, zero-collision drum arrays in `.json` format.
5. **MEI Exportation** (`src/dmp/exporters/json2mei.py`): Safely compiles array values, applies percussion layering simplifications (e.g. converting 16th spaces to 8th notes where required by MEI aesthetics), and prevents duplicate output files via suffix collision handling (`pattern_20_1.mei`).

## Installation

This project is configured using `uv` and `pyproject.toml`.

```bash
uv pip install -e .
```

## Usage

### 1. Extract Patterns from PDF to JSON
Run the `parse` orchestrator pipeline to transform a PDF file of drum tables into a canonical JSON array string.
```bash
uv run parse patterns.pdf -o output/final_dataset.json
```

### 2. Export JSON arrays to discrete MEI Scores
Run the `json2mei` utility to traverse your assembled `.json` cache and mint pristine MEI structures inside your target output folder.
```bash
uv run json2mei output/final_dataset.json -o output/mei
```

## License

This project is licensed under the [GNU General Public License v3.0 (GPL-3.0)](LICENSE) - see the `LICENSE` file for details.
