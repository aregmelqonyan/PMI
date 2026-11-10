"""Generates a clearly labeled synthetic specification so the app can be tried without any licensed PDF."""
from __future__ import annotations

import pymupdf as fitz

from .parse import PDF_LOCK

_PAGES: list[list[tuple[str, str]]] = [
    [
        ("title", "Battery Subsystem Specification (SYNTHETIC DEMO)"),
        ("body", "This document is fictional. It was written to exercise the EngiReq-AI pilot and describes no real hardware."),
        ("h", "1 Scope"),
        ("body", "This specification defines the design requirements for the battery subsystem of a fictional surface rover. "
                 "In this document the word \"shall\" indicates a binding requirement."),
        ("h", "2 Performance Requirements"),
        ("body", "The battery subsystem shall support operation for at least 120 minutes under nominal conditions. "
                 "During continuous discharge, the battery-case temperature shall not exceed 60 degrees Celsius."),
        ("body", "The total mass of the battery pack shall be no more than 18.5 kg."),
        ("body", "The bus voltage shall be 28 V ± 2 V."),
        ("body", "The charger shall operate between -20 °C and 45 °C, and the discharge circuit shall disconnect the load within 50 ms after an overcurrent event."),
        ("body", "The battery subsystem should be lightweight."),
        ("body", "Maximum allowable load: 150 N"),
        ("h", "3 Safety Requirements"),
        ("body", "The battery management unit shall not permit charging if any cell temperature is below 0 °C."),
        ("body", "The enclosure shall provide adequate protection against electrolyte leakage."),
        ("body", "The emergency disconnect shall meet the following:"),
        ("item", "a) open the main contactor within 20 ms;"),
        ("item", "b) remain open until a manual reset is performed."),
    ],
    [
        ("h", "4 Interface and Environmental Requirements"),
        ("body", "The telemetry interface shall report state of charge at a rate of at least 1 Hz. "
                 "It is recommended that diagnostic logs be retained for later analysis."),
        ("body", "The connector shall withstand no fewer than 500 mating cycles, unless replaced during scheduled maintenance."),
        ("body", "The radiator pressure shall not be less than 101 kPa."),
        ("body", "The heater power shall be TBD W during lunar night."),
        ("body", "Note: Thermal margins shall be reviewed by the design authority before each test campaign."),
        ("body", "For example, a pack might reach 40 °C after two hours of operation."),
        ("body", "The maintenance team may replace individual modules in the field."),
        ("h", "5 Verification"),
        ("body", "All requirements in this document are verified by test or analysis as described in the verification plan."),
    ],
]

_STYLES = {
    "title": ("hebo", 17, 26),
    "h": ("hebo", 12.5, 12),
    "body": ("helv", 10.5, 8),
    "item": ("helv", 10.5, 4),
}


def build_sample_pdf() -> bytes:
    margin = 64
    with PDF_LOCK:
        doc = fitz.open()
        for content in _PAGES:
            page = doc.new_page(width=595, height=842)
            y = 72.0
            for kind, text in content:
                font, size, gap = _STYLES[kind]
                indent = 18 if kind == "item" else 0
                width = page.rect.width - 2 * margin - indent
                length = fitz.get_text_length(text, fontname=font, fontsize=size)
                lines = int(length // width) + 2
                height = lines * size * 1.45
                box = fitz.Rect(margin + indent, y, page.rect.width - margin, y + height)
                page.insert_textbox(box, text, fontname=font, fontsize=size, lineheight=1.35, color=(0.1, 0.13, 0.18))
                y += (lines - 1) * size * 1.42 + gap + 6
        # A stable file ID makes the bytes reproducible, so the sample has one fixed hash.
        data = doc.tobytes(deflate=True, garbage=3, no_new_id=True)
        doc.close()
    return data
