"""OCR text cleanup: homoglyphs, split quantities, fragmented labels."""
import re
from patterns import AMT, MONEY_RE

# OCR sometimes returns Cyrillic look-alikes inside Latin words. (this was listed as a problem in the indra ocr)
_CYRILLIC = "АВЕКМНОРСТХІ" "аеорсхуі"
_LATIN = "ABEKMHOPCTXIaeopcxyi"
HOMOGLYPHS = str.maketrans(_CYRILLIC, _LATIN)

FRAGMENT_LABELS = {"total": "TOTAL", "subtotal": "SUBTOTAL", "goods": "GOODS"} # made these labels from the receipt as i was having trouble with these words if there is more words that get like this then add these here 


def _merge_split_quantities(lines):
    """Join a quantity line the OCR split into "3" / "X" / "0.79"."""
    merged = []
    i = 0

    while i < len(lines):
        if (
            i + 2 < len(lines)
            and re.fullmatch(r"\d{1,3}", lines[i])
            and re.fullmatch(r"[x@*×]", lines[i + 1], re.IGNORECASE)
            and re.fullmatch(AMT, lines[i + 2])
        ):
            merged.append(f"{lines[i]} x {lines[i + 2]}")
            i += 3
        else:
            merged.append(lines[i])
            i += 1

    return merged


def _fold(text):
    """Lower-case letters/digits only, with common OCR digit/letter swaps."""
    text = re.sub(r"[^a-z0-9]", "", text.lower())
    return text.replace("1", "l").replace("0", "o").replace("5", "s")


def _repair_fragmented_labels(lines):
    """
    OCR is splitting a label into one character per line:
    Only runs of very short lines that spell a known label are joined.
    """
    repaired = []
    i = 0

    while i < len(lines):
        replacement = None

        for size in range(3, 9):
            window = lines[i:i + size]

            if len(window) < size:
                break

            if not all(
                len(re.sub(r"\s", "", part)) <= 3 and not MONEY_RE.match(part)
                for part in window
            ):
                break

            label = FRAGMENT_LABELS.get(_fold("".join(window)))

            if label:
                replacement = (label, size)
                break

        if replacement:
            repaired.append(replacement[0])
            i += replacement[1]
        else:
            repaired.append(lines[i])
            i += 1

    return repaired


def normalize_lines(raw_text):
    """Clean OCR text while preserving its line order."""
    lines = []

    for line in raw_text.replace("\r", "\n").split("\n"):
        line = line.translate(HOMOGLYPHS)
        line = re.sub(r"\s+", " ", line).strip()

        if line:
            lines.append(line)

    lines = _merge_split_quantities(lines)
    lines = _repair_fragmented_labels(lines)

    return lines
