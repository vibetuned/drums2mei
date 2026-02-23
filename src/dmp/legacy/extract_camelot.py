import argparse
from pathlib import Path
import camelot

def main():
    parser = argparse.ArgumentParser(description="Extract table images from a PDF using Camelot")
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

    # using Lattice method since these are grid-like Drum Pattern tables
    tables = camelot.read_pdf(str(pdf_path), pages='all', flavor='lattice')
    
    print(f"Found {tables.n} table(s). Extracting...")
    
    for i, table in enumerate(tables):
        # Save to CSV
        csv_path = output_dir / f"{pdf_path.stem}_table_{i+1}.csv"
        table.df.to_csv(csv_path, index=False)
        print(f"✅ Saved Table {i+1} to {csv_path}")

if __name__ == "__main__":
    main()
