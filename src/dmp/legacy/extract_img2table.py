import argparse
import tempfile
from pathlib import Path
from PIL import Image
from img2table.document import PDF
from img2table.ocr import TesseractOCR

def main():
    parser = argparse.ArgumentParser(description="Extract table images from a PDF using img2table")
    parser.add_argument("pdf_path", type=str, help="Path to the PDF file")
    parser.add_argument("--output-dir", type=str, default=".", help="Directory to save the extracted table images")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    output_dir = Path(args.output_dir)
    
    if not pdf_path.exists():
        print(f"Error: File not found - {pdf_path}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Processing: {pdf_path}...")

    # We use Tesseract OCR if we need OCR
    # For now, let's just try to detect tables based purely on images without OCR content first
    # unless you explicitly want to extract content (since we are just outputting images for now)
    try:
        ocr = TesseractOCR(n_threads=1, lang="eng")
    except Exception as e:
        print("Tesseract not accessible, running without OCR...")
        ocr = None

    pdf = PDF(str(pdf_path))
    
    # Extract tables
    extracted_tables = pdf.extract_tables(ocr=ocr,
                                          implicit_rows=False,
                                          borderless_tables=False,
                                          min_confidence=10)

    # extracted_tables is a dict: {page_number: [Table, ...]}
    table_count = sum(len(tables) for tables in extracted_tables.values())
    if table_count == 0:
        print("No tables found in the document.")
        return

    print(f"Found {table_count} table(s). Extracting images...")
    
    # Open the PDF with PyMuPDF to extract images based on bounding boxes
    import fitz # PyMuPDF
    import io
    doc = fitz.open(pdf_path)
    
    table_idx = 1
    import pandas as pd
    
    for page_num, tables in extracted_tables.items():
        if not tables:
            continue
            
        page = doc[page_num] # PyMuPDF is 0-indexed like img2table's output keys
        
        # Sort tables by vertical position
        tables = sorted(tables, key=lambda t: t.bbox.y1)
        
        class MergedTable:
            def __init__(self, x1, y1, x2, y2, df):
                self.x1 = x1
                self.y1 = y1
                self.x2 = x2
                self.y2 = y2
                self.df = df
                
        merged = []
        curr = tables[0]
        curr_merged = MergedTable(curr.bbox.x1, curr.bbox.y1, curr.bbox.x2, curr.bbox.y2, curr.df)
        
        for nxt in tables[1:]:
            vert_dist = nxt.bbox.y1 - curr_merged.y2
            # Tables belonging to the same grid are usually very close. We use 50 pixels as a max gap.
            if vert_dist < 50:
                curr_merged.x1 = min(curr_merged.x1, nxt.bbox.x1)
                curr_merged.y1 = min(curr_merged.y1, nxt.bbox.y1)
                curr_merged.x2 = max(curr_merged.x2, nxt.bbox.x2)
                curr_merged.y2 = max(curr_merged.y2, nxt.bbox.y2)
                if curr_merged.df is not None and nxt.df is not None:
                    curr_merged.df = pd.concat([curr_merged.df, nxt.df], ignore_index=True)
                elif nxt.df is not None:
                    curr_merged.df = nxt.df
            else:
                merged.append(curr_merged)
                curr_merged = MergedTable(nxt.bbox.x1, nxt.bbox.y1, nxt.bbox.x2, nxt.bbox.y2, nxt.df)
        merged.append(curr_merged)
        
        for table in merged:
            scale = 72 / 200
            
            x1, y1, x2, y2 = table.x1, table.y1, table.x2, table.y2
            
            # Create a PyMuPDF Rect, scaled down to 72 DPI points
            rect = fitz.Rect(x1 * scale, y1 * scale, x2 * scale, y2 * scale)
            
            # Crop the page and save the image at high resolution (e.g. 300 DPI for zooming)
            zoom = 300 / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, clip=rect)
            
            image_path = output_dir / f"{pdf_path.stem}_table_{table_idx}.png"
            pix.save(str(image_path))
            
            csv_path = output_dir / f"{pdf_path.stem}_table_{table_idx}.csv"
            if table.df is not None and not table.df.empty:
                table.df.to_csv(csv_path, index=False)
                
            print(f"✅ Saved Table {table_idx} (Image and CSV) to {output_dir}")
            
            table_idx += 1

if __name__ == "__main__":
    main()
