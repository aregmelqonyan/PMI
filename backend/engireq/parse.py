"""PDF parsing that keeps page, block and character-level coordinates.

Block text is the immutable source string every evidence offset points into.
PyMuPDF is not thread-safe, so all document access goes through ``PDF_LOCK``.
"""
from __future__ import annotations

import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import pymupdf as fitz

PDF_LOCK = threading.RLock()

Rect = tuple[float, float, float, float]

_TEXT_FLAGS = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP
_LIST_MARKER = re.compile(r"^\s*(?:[•·▪◦●\-–*]\s+|\(?[a-zA-Z]\)\s+|\(?\d{1,2}\)\s+|\d{1,2}\.\s+(?=\S)(?!\d))")


@dataclass
class Block:
    block_id: str
    page: Optional[int]
    text: str
    bbox: Rect = (0.0, 0.0, 0.0, 0.0)
    char_rects: list[Optional[Rect]] = field(default_factory=list)
    char_lines: list[int] = field(default_factory=list)
    line_starts: list[int] = field(default_factory=list)
    max_font: float = 0.0
    bold: bool = False

    def rects_for(self, start: int, end: int) -> list[list[float]]:
        """One rectangle per text line covered by [start, end), in PDF points."""
        by_line: dict[int, list[float]] = {}
        for i in range(start, min(end, len(self.char_rects))):
            rect = self.char_rects[i]
            if rect is None:
                continue
            line = self.char_lines[i]
            if line not in by_line:
                by_line[line] = list(rect)
            else:
                box = by_line[line]
                box[0] = min(box[0], rect[0])
                box[1] = min(box[1], rect[1])
                box[2] = max(box[2], rect[2])
                box[3] = max(box[3], rect[3])
        return [[round(v, 2) for v in by_line[k]] for k in sorted(by_line)]


@dataclass
class ParsedDocument:
    blocks: list[Block]
    pages: list[dict]
    warnings: list[str]


def _block_from_lines(block_id: str, page_no: int, raw_lines: list[dict]) -> Optional[Block]:
    text: list[str] = []
    rects: list[Optional[Rect]] = []
    lines: list[int] = []
    starts: list[int] = []
    max_font = 0.0
    bold_chars = total_chars = 0

    for line_index, line in enumerate(raw_lines):
        chars = [(c["c"], tuple(c["bbox"]), span) for span in line["spans"] for c in span["chars"]]
        # Collapse justification runs so that one space separates words.
        collapsed = []
        for ch, box, span in chars:
            if ch.isspace():
                if not collapsed or collapsed[-1][0] == " ":
                    continue
                ch = " "
            collapsed.append((ch, box, span))
        while collapsed and collapsed[-1][0] == " ":
            collapsed.pop()
        if not collapsed:
            continue

        if text:
            # A word broken at a line end keeps its hyphen: the source is not rewritten.
            joined_word = text[-1] == "-" and len(text) > 1 and text[-2].isalpha() and collapsed[0][0].islower()
            if not joined_word:
                text.append(" ")
                rects.append(None)
                lines.append(line_index)
        starts.append(len(text))
        for ch, box, span in collapsed:
            text.append(ch)
            rects.append(box)
            lines.append(line_index)
            max_font = max(max_font, span["size"])
            total_chars += 1
            if span["flags"] & 16 or "bold" in span["font"].lower():
                bold_chars += 1

    if not text:
        return None
    boxes = [r for r in rects if r]
    bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    return Block(block_id, page_no, "".join(text), bbox, rects, lines, starts, max_font, bold_chars > total_chars * 0.6)


def parse_pdf(path: str) -> ParsedDocument:
    blocks: list[Block] = []
    pages: list[dict] = []
    warnings: list[str] = []
    no_text_pages: list[int] = []

    with PDF_LOCK, fitz.open(path) as doc:
        if doc.needs_pass:
            raise ValueError("This PDF is password protected.")
        for page_index, page in enumerate(doc):
            page_no = page_index + 1
            pages.append({"page": page_no, "width": round(page.rect.width, 2), "height": round(page.rect.height, 2)})
            raw = page.get_text("rawdict", flags=_TEXT_FLAGS)
            block_no = 0
            page_chars = 0
            for raw_block in raw["blocks"]:
                if raw_block.get("type") != 0:
                    continue
                # Rotated text such as margin stamps is not part of the reading flow.
                lines = [l for l in raw_block["lines"] if abs(l["dir"][0] - 1) < 0.01]
                block_no += 1
                block = _block_from_lines(f"p{page_no:03d}b{block_no:03d}", page_no, lines)
                if block:
                    blocks.append(block)
                    page_chars += len(block.text)
            if page_chars < 20:
                no_text_pages.append(page_no)

    if no_text_pages:
        shown = ", ".join(map(str, no_text_pages[:12])) + ("…" if len(no_text_pages) > 12 else "")
        warnings.append(
            f"{len(no_text_pages)} of {len(pages)} pages have no usable text layer (pages {shown}). "
            "OCR is not run, so these pages were not analyzed."
        )
    removed = _drop_page_furniture(blocks, pages)
    if removed:
        warnings.append(f"{removed} repeated header/footer blocks were excluded from analysis.")
    if not blocks:
        warnings.append("No extractable text was found in this PDF.")
    return ParsedDocument(blocks, pages, warnings)


def _drop_page_furniture(blocks: list[Block], pages: list[dict]) -> int:
    """Remove running headers and footers: same text (ignoring digits) in the page margins of many pages."""
    if len(pages) < 3:
        return 0
    heights = {p["page"]: p["height"] for p in pages}

    def in_margin(block: Block) -> bool:
        height = heights[block.page]
        return block.bbox[3] < height * 0.11 or block.bbox[1] > height * 0.89

    def key(block: Block) -> str:
        return re.sub(r"\d+", "#", block.text.strip().lower())

    pages_with = Counter()
    for block in blocks:
        if in_margin(block):
            pages_with[key(block)] += 1
    threshold = max(3, int(len(pages) * 0.3))
    repeated = {k for k, n in pages_with.items() if n >= threshold}
    keep = [b for b in blocks if not (in_margin(b) and key(b) in repeated)]
    removed = len(blocks) - len(keep)
    blocks[:] = keep
    return removed


def text_block(text: str, block_id: str = "b001") -> Block:
    """Wrap plain text as a single block with no page geometry (used by the playground)."""
    return Block(block_id, None, text, line_starts=[0])


def is_list_item(text: str) -> bool:
    return bool(_LIST_MARKER.match(text))


def list_marker_end(text: str) -> int:
    match = _LIST_MARKER.match(text)
    return match.end() if match else 0


def render_page_png(path: str, page_no: int, zoom: float = 2.0) -> bytes:
    with PDF_LOCK, fitz.open(path) as doc:
        if not 1 <= page_no <= doc.page_count:
            raise IndexError(page_no)
        pixmap = doc[page_no - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pixmap.tobytes("png")
