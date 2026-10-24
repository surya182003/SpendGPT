from pathlib import Path
import contextlib
import io
import json
import sys
import traceback

# Directory containing this script: database/ocr/
OCR_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(OCR_DIR))

# my parser for receipts, which uses Indra OCR to extract text from images - change this to your own parser if you want to use a different OCR engine
from receipt_parser import parse_receipt_text, validate_receipt

DEFAULT_IMAGE = OCR_DIR / "test_images" / "aldi_test.jpeg"


def run_indra_ocr(image_path):
    """Run Indra OCR on an image and return the recognised text as a string."""
    from indra_ocr.cli import main as indra_main

    old_argv = sys.argv
    sys.argv = ["indra-ocr", str(image_path), "--format", "text"]

    buffer = io.StringIO()

    try:
        # The CLI prints its result to stdout, so capture it.
        with contextlib.redirect_stdout(buffer):
            indra_main()
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise RuntimeError(f"Indra OCR exited with code {exc.code}")
    finally:
        sys.argv = old_argv

    return buffer.getvalue()


def process_receipt(image_path):
    image_path = Path(image_path)

    if not image_path.is_file():
        raise FileNotFoundError(f"Receipt image not found: {image_path}")

    raw_text = run_indra_ocr(image_path)

    if not raw_text.strip():
        raise RuntimeError("Indra OCR returned no text.")

    result = parse_receipt_text(raw_text)
    return validate_receipt(result)


def main():
    image_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMAGE

    print("Python:", sys.executable)
    print("Image:", image_path)

    try:
        result = process_receipt(image_path)
    except Exception:
        print("\nReceipt processing failed:")
        traceback.print_exc()
        return

    print("\n--- RAW OCR TEXT ---\n")
    print(result["raw_ocr_text"])

    print("\n--- PARSED RECEIPT ---\n")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()