import argparse
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
from docling.datamodel.pipeline_options import TableFormerMode

def process_pdf(pdf_path: Path, output_dir: Path):
    """Processes the PDF and extracts table images."""
    
    print(f"Processing: {pdf_path}...")

    # Enable table images in Docling
    pipeline_options = PdfPipelineOptions()
    pipeline_options.generate_table_images = True
    pipeline_options.do_ocr = True # ensure OCR is on for scanned files
    
    # Configure TableFormer for maximum accuracy
    pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
    pipeline_options.table_structure_options.do_cell_matching = False

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    
    print("Extracting tables using Docling...")
    result = converter.convert(pdf_path)

    tables = result.document.tables
    if not tables:
        print("No tables found in the document.")
        return

    print(f"Found {len(tables)} table(s). Extracting images...")
    
    for i, table in enumerate(tables):
        # Extract the image of the table
        image = None
        if hasattr(table, "get_image"):
            image = table.get_image(result.document)

        if image:
            # Save the image
            image_path = output_dir / f"{pdf_path.stem}_table_{i+1}.png"
            image.save(image_path)
            print(f"✅ Saved Table {i+1} image to {image_path}")
        else:
            print(f"⚠️ Could not extract image for Table {i+1}")

def main():
    parser = argparse.ArgumentParser(description="Extract table images from a PDF using Docling")
    parser.add_argument("pdf_path", type=str, help="Path to the PDF file")
    parser.add_argument("--output-dir", type=str, default=".", help="Directory to save the extracted table images")
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
