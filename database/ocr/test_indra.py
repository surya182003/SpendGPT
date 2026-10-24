
from pathlib import Path
import sys
import traceback

# Directory containing this script: database/ocr/
OCR_DIR = Path(__file__).resolve().parent

IMAGE_PATH = OCR_DIR / "test_images" / "test1.jpeg"


def main():
    print("Python:", sys.executable)
    print("Image:", IMAGE_PATH)

    if not IMAGE_PATH.is_file():
        print(f"ERROR: Receipt image not found: {IMAGE_PATH}")
        return

    try:
        from indra_ocr.cli import main as indra_main

        sys.argv = [
            "indra-ocr",
            str(IMAGE_PATH),
            "--format",
            "text",
        ]

        print("\n--- INDRA OCR OUTPUT ---\n")
        indra_main()

    except SystemExit as exc:
        if exc.code not in (None, 0):
            print("Indra OCR exited with code:", exc.code)
    except Exception:
        print("\nOCR failed:")
        traceback.print_exc()


if __name__ == "__main__":
    main()
