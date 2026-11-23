import os
import sys
import tempfile
from pathlib import Path

# The OCR code lives in database/ocr, so add that folder to the path to import it
OCR_DIR = Path(__file__).resolve().parents[3] / "database" / "ocr"
if str(OCR_DIR) not in sys.path:
    sys.path.insert(0, str(OCR_DIR))

from ocr import process_receipt


def read_receipt(file_bytes, filename):
    # OCR needs a file path, so save the upload to a temp file first
    suffix = Path(filename or "").suffix or ".jpg"

    # delete=False otherwise it doesn't work on windows
    temp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        temp.write(file_bytes)
        temp.close()
        return process_receipt(temp.name)
    finally:
        os.remove(temp.name)
