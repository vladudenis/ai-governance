"""Plain-text extraction from Formex elements.

Formex uses non-breaking spaces and splits headings across elements. The
extracted string keeps the words in document order and collapses that layout
whitespace. Footnote bodies are returned separately so they do not break the
sentence they are attached to.
"""

import re
from xml.etree import ElementTree as ET

_SPACE_BEFORE = {"TI", "STI", "P", "ALINEA", "TXT", "VISA", "ITEM", "NO.P", "NO.PARAG", "LIST"}


def extract_text(element: ET.Element) -> tuple[str, list[str]]:
    """Return normalised wording and footnote texts for ``element``."""
    chunks: list[str] = []
    notes: list[str] = []

    def walk(node: ET.Element) -> None:
        if node.text:
            chunks.append(node.text)
        for child in list(node):
            if child.tag == "NOTE":
                note_text, nested_notes = extract_text(child)
                if note_text:
                    notes.append(note_text)
                notes.extend(nested_notes)
            else:
                if child.tag in _SPACE_BEFORE:
                    chunks.append(" ")
                walk(child)
            if child.tail:
                chunks.append(child.tail)

    walk(element)
    return normalize_whitespace("".join(chunks)), notes


def normalize_whitespace(value: str) -> str:
    """Collapse Formex layout spaces into single spaces."""
    value = value.replace("\xa0", " ").replace("\u202f", " ").replace("\u00ad", "")
    return re.sub(r"\s+", " ", value).strip()


def point_number(raw: str) -> str:
    """Turn ``(a)``, ``(iii)`` or ``1.`` into the token used in a citation."""
    return raw.strip().strip("()").rstrip(".")
