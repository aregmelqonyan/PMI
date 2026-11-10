"""Baseline B0: deterministic segmentation, detection and field extraction (proposal section 4.6).

Every decision adds a readable entry to the record's ``trace``, so a reviewer can see which rule fired.
All offsets are absolute character positions in the block's immutable text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from . import BASELINE_VERSION
from .parse import Block, is_list_item, list_marker_end
from .schema import Constraint, Evidence, Passage, Requirement
from .units import NUMBER, UNIT, canonical_unit, dimension, parse_number

# --- segmentation -----------------------------------------------------------------------------

_ABBREVIATIONS = {
    "e.g", "i.e", "etc", "fig", "figs", "no", "nos", "vs", "approx", "max", "min", "ref", "refs",
    "sec", "eq", "eqs", "al", "std", "vol", "dr", "mr", "ms", "cf", "para", "rev", "ver", "incl", "nom",
}
_SENTENCE_END = re.compile(r"[.!?]\]?(?=\s+[\"“(\[]?[A-Z0-9])")
_INLINE_LABEL = re.compile(r"\[[A-Z]{1,6}\d*[ -]\d{2,}[^\]]{0,12}\]")
_LINE_HEADING = re.compile(r"\d+(?:\.\d+)+\.?\s+[A-Z]")
_RATIONALE_START = re.compile(r"\s*\[\s*rationale\b", re.I)
_HEADING = re.compile(r"^(?:(?:section\s+)?\d+(?:\.\d+)*\.?|[A-Z]\.\d+(?:\.\d+)*|appendix\s+[A-Z])\s+\S", re.I)
_LEADING_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)+\.?|[A-Z]\.\d+(?:\.\d+)*)\s+")
_SOURCE_LABEL = re.compile(r"^\s*(?:\d+(?:\.\d+)+\.?\s+)?(?:\[([A-Za-z0-9][A-Za-z0-9 ._\-]{0,24})\]|([A-Z]{1,6}\d*[ -]\d{3,})\b)\s*")
_TOC_LINE = re.compile(r"(?:\.\s?){4,}\s*\d+\s*$")


@dataclass
class Segment:
    block: Block
    start: int
    end: int

    @property
    def text(self) -> str:
        return self.block.text[self.start:self.end]


def _trim(text: str, start: int, end: int, punctuation: str = "") -> tuple[int, int]:
    strip = set(" \t\n ") | set(punctuation)
    while start < end and text[start] in strip:
        start += 1
    while end > start and text[end - 1] in strip:
        end -= 1
    return start, end


def segment_block(block: Block) -> list[Segment]:
    text = block.text
    # List markers at the start of a line begin a new passage.
    cuts = {0, len(text)}
    for line_start in block.line_starts[1:]:
        if is_list_item(text[line_start:line_start + 12]) or _LINE_HEADING.match(text, line_start):
            cuts.add(line_start)
    # Standards often place a requirement ID such as [V2 8057] mid-block, right after a heading.
    for match in _INLINE_LABEL.finditer(text):
        cuts.add(match.start())
    for match in _SENTENCE_END.finditer(text):
        word = re.search(r"([\w.]+)$", text[: match.start()])
        token = word.group(1).lower() if word else ""
        if token in _ABBREVIATIONS or (len(token) == 1 and token.isalpha()):
            continue
        cuts.add(match.end())
    ordered = sorted(cuts)
    segments = []
    for start, end in zip(ordered, ordered[1:]):
        s, e = _trim(text, start, end)
        if e > s:
            segments.append(Segment(block, s, e))
    return segments


# --- cue patterns -----------------------------------------------------------------------------

_MANDATORY = re.compile(r"\b(?:shall|must|(?:is|are)\s+required\s+to)(?:\s+(?:not|never))?\b", re.I)
_RECOMMENDED = re.compile(r"\b(?:should|is\s+recommended|are\s+recommended)\b", re.I)
_PERMITTED = re.compile(r"\b(?:may|can)\b", re.I)
_NOTE = re.compile(r"^\s*(?:notes?|rationale|comment|explanation|informative)\s*(?:\d+\s*)?[:\-–—]", re.I)
_EXAMPLE = re.compile(r"^\s*(?:for\s+example|for\s+instance|example\s*(?:\d+\s*)?[:\-–—]|e\.g\.)", re.I)
_MODAL_MENTION = re.compile(
    r"[\"“‘']\s*(?:shall|must|should|may|will)\s*[\"”’']"
    r"|\b(?:word|term|verb|keyword)s?\s+(?:shall|must)\b"
    r"|\b(?:shall|must)\s+(?:be\s+(?:understood|interpreted)\s+(?:as|to)|denotes?|means?|indicates?)\b",
    re.I,
)
_IMPLICIT = re.compile(
    rf"^\s*(?:the\s+)?(?P<kw>maximum|minimum|max\.?|min\.?)\s+(?P<name>[^:=]{{1,60}}?)\s*[:=]\s*"
    rf"(?P<num>{NUMBER})\s*(?P<unit>{UNIT})",
    re.I,
)
_QUOTED = re.compile(r"[\"“][^\"”]*[\"”]")

_LEADING_CONDITION = re.compile(
    r"^\s*(?:during|when|whenever|while|if|under|in\s+the\s+event|upon|after|before|prior\s+to|following"
    r"|throughout|for|in|at|on)\b",
    re.I,
)
_TRAILING_CONDITION = re.compile(
    r"\b(?:during|when|whenever|while|under(?!\s+[-−]?\d)|in\s+the\s+event|upon|prior\s+to|after|before"
    r"|throughout|at\s+all\s+times|if|(?:at|in)\s+(?:temperatures?|pressures?|altitudes?|ambient))\b",
    re.I,
)
_EXCEPTION = re.compile(r"\b(?:unless|except)\b", re.I)
_CLAUSE_CONNECTIVE = re.compile(r";|,\s*(?:and|or|while|but)\b|\b(?:and|or)\b", re.I)

_FILLER_WORDS = (
    r"a|an|the|its|total|value|level|limit|rate|temperature|pressure|mass|weight|voltage|current|power"
    r"|load|force|speed|length|duration|period|of|by"
)
_FILLER = rf"(?:\s+(?:{_FILLER_WORDS})){{0,4}}"

_COMPARATORS: list[tuple[str, str]] = [
    (r"(?:less|lower|smaller)\s+than\s+or\s+equal\s+to", "<="),
    (r"(?:greater|more|higher)\s+than\s+or\s+equal\s+to", ">="),
    (r"at\s+most|up\s+to|(?:a\s+)?maximum(?:\s+value)?\s+of|within", "<="),
    (r"at\s+least|(?:a\s+)?minimum(?:\s+value)?\s+of", ">="),
    (r"exceed(?:s|ing)?|greater\s+than|more\s+than|higher\s+than|larger\s+than|longer\s+than|above|over", ">"),
    (r"less\s+than|fewer\s+than|lower\s+than|smaller\s+than|shorter\s+than|below|under|beneath", "<"),
    (r"equal\s+to|exactly", "="),
]
_SYMBOLS = [("≤", "<="), ("<=", "<="), ("≥", ">="), (">=", ">="), ("<", "<"), (">", ">"), ("=", "=")]
_WORD_ALTERNATION = "|".join(p for p, _ in _COMPARATORS)
_SYMBOL_ALTERNATION = "|".join(re.escape(s) for s, _ in _SYMBOLS)
_COMPARATOR_RE = re.compile(
    rf"(?:\b(?P<word>{_WORD_ALTERNATION})\b{_FILLER}|(?P<sym>{_SYMBOL_ALTERNATION})(?:\s*\([a-z ]{{4,40}}\))?)\s*"
    rf"(?P<num>{NUMBER})(?:\s*(?P<unit>{UNIT}))?",
    re.I,
)
_NEGATION_BEFORE = re.compile(r"\b(not|never|no)\b(?:\s+[\w-]+){0,3}\s*$", re.I)
_FLIP = {"<": ">=", ">": "<=", "<=": ">", ">=": "<"}

_RANGE_BETWEEN = re.compile(
    rf"\b(?:between|from)\s+(?P<a>{NUMBER})(?:\s*(?P<ua>{UNIT}))?\s+(?:and|to)\s+(?P<b>{NUMBER})\s*(?P<ub>{UNIT})", re.I
)
_RANGE_DASH = re.compile(
    rf"(?P<a>{NUMBER})(?:\s*(?P<ua>{UNIT}))?\s*(?:to|–|—)\s*(?P<b>{NUMBER})\s*(?P<ub>{UNIT})"
)
_TOLERANCE = re.compile(rf"(?P<a>{NUMBER})(?:\s*(?P<ua>{UNIT}))?\s*(?:±|\+/-|\+/−)\s*(?P<b>{NUMBER})\s*(?P<ub>{UNIT})")
_BARE_EQUAL = re.compile(rf"\bbe\s+(?P<num>{NUMBER})\s*(?P<unit>{UNIT})", re.I)
_BARE_QUANTITY = re.compile(rf"(?P<num>{NUMBER})\s*(?P<unit>{UNIT})")

_PARAMETER_NOUNS = {
    "temperature", "pressure", "voltage", "current", "mass", "weight", "power", "frequency", "force", "load",
    "speed", "velocity", "acceleration", "duration", "length", "width", "height", "diameter", "thickness",
    "capacity", "torque", "resistance", "humidity", "level", "rate", "flow", "time", "life", "lifetime",
    "concentration", "noise", "efficiency", "latency",
}
_PARAM_OF_COMPONENT = re.compile(r"^(?P<param>.{1,80}?)\s+of\s+(?:the\s+|each\s+|any\s+|all\s+)?(?P<comp>.{1,120})$", re.I)
_ARTICLE = re.compile(r"^(?:the|a|an|each|every|all|any)\s+", re.I)
_PRONOUN_SUBJECT = re.compile(r"^(?:it|this|that|these|those|they|he|she|which)$", re.I)

_VAGUE = re.compile(
    r"\b(?:adequate(?:ly)?|appropriate(?:ly)?|sufficient(?:ly)?|suitable|reasonable|user[- ]friendly|easy|easily"
    r"|robust|lightweight|high\s+reliability|highly\s+reliable|as\s+(?:required|necessary|needed|appropriate)"
    r"|minimi[sz]e|maximi[sz]e|if\s+possible|where\s+practical|fast|quickly|timely|efficient(?:ly)?)\b",
    re.I,
)
_TBD = re.compile(r"\b(?:TBD|TBR|TBC)\b")
_UNCLEAR_REF = re.compile(r"\b(?:as\s+(?:stated|described|specified)\s+above|see\s+above|the\s+above|aforementioned)\b", re.I)

_SAFETY = re.compile(r"\b(?:safe|safety|hazard\w*|emergenc\w+|injur\w+|fail-safe|toxic\w*|fire|flammab\w+|explos\w+|crew\s+safety)\b", re.I)
_INTERFACE = re.compile(r"\b(?:interface\w*|connector\w*|protocol\w*|compatible|bus|communicat\w+|API|telemetry|mating)\b", re.I)
_ENVIRONMENT = re.compile(r"\b(?:ambient|environment\w*|humidity|vibration\w*|radiation|shock|altitude|corrosi\w+|vacuum)\b", re.I)


# --- classification ---------------------------------------------------------------------------


def _mask_quotes(text: str) -> str:
    return _QUOTED.sub(lambda m: " " * len(m.group(0)), text)


def _classify(text: str) -> tuple[bool, str, str]:
    """Return (candidate, modality, reason)."""
    stripped = text.strip()
    if _TOC_LINE.search(stripped):
        return False, "informational", "Table-of-contents line"
    if _NOTE.match(stripped):
        return False, "informational", "Note or rationale text"
    if _EXAMPLE.match(stripped):
        return False, "informational", "Illustrative example"
    if _MODAL_MENTION.search(stripped):
        return False, "informational", "Defines or mentions a modal verb"
    if stripped.endswith("?"):
        return False, "informational", "Question"
    masked = _mask_quotes(stripped)
    if _MANDATORY.search(masked):
        return True, "mandatory", "Mandatory modal cue"
    if _IMPLICIT.match(stripped):
        return True, "mandatory", "Implicit limit pattern"
    if _RECOMMENDED.search(masked):
        return False, "recommended", "Recommendation, not a binding requirement"
    if _PERMITTED.search(masked):
        return False, "permitted", "Permission, not a binding requirement"
    if _HEADING.match(stripped) and len(stripped) < 100 and not stripped.endswith("."):
        return False, "informational", "Section heading"
    return False, "informational", "No requirement cue"


def _split_atomic(text: str, offset: int) -> list[tuple[int, int]]:
    """Split one sentence into one clause per mandatory modal, using connectives between them."""
    masked = _mask_quotes(text)
    modals = list(_MANDATORY.finditer(masked))
    if len(modals) < 2:
        return [(offset, offset + len(text))]
    cuts = []
    for previous, current in zip(modals, modals[1:]):
        between = masked[previous.end(): current.start()]
        connectives = list(_CLAUSE_CONNECTIVE.finditer(between))
        if connectives:
            cuts.append(previous.end() + connectives[-1].start())
    spans, start = [], 0
    for cut in cuts:
        spans.append((offset + start, offset + cut))
        start = cut
    spans.append((offset + start, offset + len(text)))
    return spans


@dataclass
class Inherited:
    subject: Optional[tuple[int, int, Block]] = None
    negated: bool = False
    subject_text: Optional[str] = None


class Extractor:
    """Extract atomic records from segments of one document."""

    def __init__(self, document_id: str, sha256: str):
        self.document_id = document_id
        self.sha256 = sha256
        self.record_count = 0
        self.span_count = 0
        self.section: Optional[str] = None

    def next_span(self, block: Block) -> str:
        self.span_count += 1
        page = f"p{block.page:02d}" if block.page else "p00"
        return f"{self.document_id}:{page}:{block.block_id}:{self.span_count:04d}"

    def run(self, blocks: list[Block]) -> tuple[list[Passage], list[Requirement]]:
        passages: list[Passage] = []
        records: list[Requirement] = []
        # A flat list keeps list stems visible across block boundaries.
        all_segments = [(b, s) for b in blocks for s in segment_block(b)]
        stem: Optional[Inherited] = None
        in_rationale = False
        for index, (block, segment) in enumerate(all_segments):
            self._update_section(segment)
            text = segment.text
            candidate, modality, reason = _classify(text)
            # A bracketed rationale can span several sentences, and its "must" is explanation.
            if _RATIONALE_START.match(text) or (in_rationale and not _SOURCE_LABEL.match(text)):
                candidate, modality, reason = False, "informational", "Rationale text"
                in_rationale = not text.rstrip(" .").endswith("]")
            else:
                in_rationale = False
            span_id = self.next_span(block)
            passage = Passage(
                span_id=span_id, document_id=self.document_id, page=block.page, block_id=block.block_id,
                section=self.section, start_char=segment.start, end_char=segment.end, text=text,
                rects=block.rects_for(segment.start, segment.end), detected=candidate, modality=modality, reason=reason,
            )
            next_is_item = index + 1 < len(all_segments) and is_list_item(all_segments[index + 1][1].text)
            item = is_list_item(text)

            if candidate and text.rstrip().endswith(":") and next_is_item and _MANDATORY.search(_mask_quotes(text)):
                stem = self._stem_context(segment)
                passage.reason = "Mandatory list stem; items become records"
            elif item and stem is not None and not candidate and modality == "informational" and reason == "No requirement cue":
                passage.detected = True
                passage.modality = "mandatory"
                passage.reason = "List item under a mandatory stem"
                record = self._build(segment, span_id, segment.start, segment.end, inherited=stem)
                records.append(record)
                passage.record_ids.append(record.requirement_id)
            else:
                if not item:
                    stem = None
                if candidate:
                    implicit = _IMPLICIT.match(text)
                    if implicit and not _MANDATORY.search(_mask_quotes(text)):
                        record = self._build_implicit(segment, span_id, implicit)
                        records.append(record)
                        passage.record_ids.append(record.requirement_id)
                    else:
                        inherited: Optional[Inherited] = None
                        for clause_start, clause_end in _split_atomic(text, segment.start):
                            s, e = _trim(block.text, clause_start, clause_end, ",;")
                            s = self._skip_connective(block.text, s, e)
                            record = self._build(segment, span_id, s, e, inherited=inherited, sibling=inherited is not None)
                            records.append(record)
                            passage.record_ids.append(record.requirement_id)
                            if inherited is None:
                                inherited = self._context_from(record)
            passages.append(passage)
        return passages, records

    @staticmethod
    def _skip_connective(text: str, start: int, end: int) -> int:
        match = re.match(r"(?:and|or|while|but)\b\s*", text[start:end], re.I)
        return start + match.end() if match else start

    def _update_section(self, segment: Segment) -> None:
        text = segment.text.strip()
        if _HEADING.match(text) and len(text) < 100 and not text.endswith(".") and not _MANDATORY.search(text) and not _TOC_LINE.search(text):
            self.section = text
        else:
            number = _LEADING_NUMBER.match(text)
            if number and _MANDATORY.search(text):
                self.section = number.group(1).rstrip(".")

    @staticmethod
    def _context_from(record: Requirement) -> Inherited:
        return Inherited(subject_text=record.component or record.action_or_state, negated=False)

    def _stem_context(self, segment: Segment) -> Inherited:
        masked = _mask_quotes(segment.text)
        modal = _MANDATORY.search(masked)
        subject_start, subject_end = segment.start, segment.start + modal.start()
        subject = self._subject_text(segment.block.text, subject_start, subject_end)
        return Inherited(subject_text=subject, negated=bool(re.search(r"\b(?:not|never)\b", modal.group(0), re.I)))

    @staticmethod
    def _subject_text(text: str, start: int, end: int) -> Optional[str]:
        start, end = _trim(text, start, end, ",;:")
        label = _SOURCE_LABEL.match(text[start:end])
        if label:
            start += label.end()
        number = _LEADING_NUMBER.match(text[start:end])
        if number:
            start += number.end()
        marker = list_marker_end(text[start:end])
        start += marker
        chunk = text[start:end].strip()
        # A title left in front of the sentence ends where a capitalized article starts: "Food Quality The food system".
        titled = list(re.finditer(r"(?<=[a-z\])]\s)(?:The|Each|All|Any)\s", chunk))
        if titled:
            chunk = chunk[titled[-1].start():]
        chunk = _ARTICLE.sub("", chunk)
        return chunk or None

    def _new_id(self) -> str:
        self.record_count += 1
        return f"req_{self.document_id.removeprefix('doc_')}_{self.record_count:03d}"

    def _evidence(self, block: Block, section: Optional[str], start: int, end: int) -> Evidence:
        return Evidence(page=block.page, section=section, block_id=block.block_id, start_char=start, end_char=end,
                        quoted_text=block.text[start:end], rects=block.rects_for(start, end))

    def _build_implicit(self, segment: Segment, span_id: str, match: re.Match) -> Requirement:
        block = segment.block
        keyword = match.group("kw").lower()
        operator = "<=" if keyword.startswith("max") else ">="
        value, decimal_comma = parse_number(match.group("num"))
        unit = canonical_unit(match.group("unit"))
        surface_start = segment.start + match.start("kw")
        surface_end = segment.start + match.end("unit")
        flags = ["implicit_requirement"] + (["decimal_comma"] if decimal_comma else [])
        name = match.group("name").strip()
        return Requirement(
            requirement_id=self._new_id(), document_id=self.document_id, source_sha256=self.sha256, span_id=span_id,
            requirement_type="performance", component=None, action_or_state=name,
            constraints=[Constraint(parameter=self._parameter(unit, name, flags), operator=operator, value=value, unit=unit,
                                    surface_text=block.text[surface_start:surface_end], start_char=surface_start, end_char=surface_end)],
            evidence=self._evidence(block, self.section, segment.start, segment.end),
            quality_flags=flags, trace=[f"implicit:{keyword} … : value", f"operator:{keyword}→{operator}"], method=BASELINE_VERSION,
        )

    @staticmethod
    def _parameter(unit: Optional[str], subject: Optional[str], flags: list[str]) -> Optional[str]:
        dim = dimension(unit)
        if dim == "mass_or_acceleration":
            flags.append("ambiguous_unit")
            return None
        return dim

    def _build(self, segment: Segment, span_id: str, start: int, end: int,
               inherited: Optional[Inherited] = None, sibling: bool = False) -> Requirement:
        block = segment.block
        text = block.text
        clause = text[start:end]
        masked = _mask_quotes(clause)
        modal = _MANDATORY.search(masked)
        trace: list[str] = []
        flags: list[str] = []

        if modal:
            modal_start, modal_end = start + modal.start(), start + modal.end()
            negated = bool(re.search(r"\b(?:not|never)\b", modal.group(0), re.I))
            trace.append(f"modal:{re.sub(chr(92) + 's+', ' ', modal.group(0)).lower()}")
        else:  # list item under a stem
            modal_start = modal_end = start + list_marker_end(clause)
            negated = bool(inherited and inherited.negated)
            trace.append("modal:inherited from list stem")

        # Conditions and exceptions are located first, so numbers inside them are not read as limits.
        condition_span: Optional[tuple[int, int]] = None
        # A requirement ID or section number in front must not hide a leading condition.
        body_start = start
        for prefix in (_SOURCE_LABEL, _LEADING_NUMBER):
            found_prefix = prefix.match(text[body_start:modal_start])
            if found_prefix:
                body_start += found_prefix.end()
        subject_start = start
        leading = _LEADING_CONDITION.match(text[body_start:modal_start]) if modal_start > body_start else None
        if leading:
            comma = text.find(",", body_start, modal_start)
            if comma != -1:
                condition_span = _trim(text, body_start, comma, ",")
                subject_start = comma + 1
                trace.append("condition:leading clause")

        exception_span: Optional[tuple[int, int]] = None
        exception = _EXCEPTION.search(text, modal_end, end)
        region_end = end
        if exception:
            exception_span = _trim(text, exception.start(), end, ".,;")
            region_end = exception.start()
            trace.append("exception:unless/except clause")
        if condition_span is None:
            trailing = _TRAILING_CONDITION.search(text, modal_end, region_end)
            if trailing:
                condition_span = _trim(text, trailing.start(), region_end, ".,;")
                region_end = trailing.start()
                trace.append("condition:trailing clause")

        condition_text = text[condition_span[0]:condition_span[1]] if condition_span else None
        constraints, first_comparator = self._constraints(text, modal_start, modal_end, region_end, condition_text, flags, trace)

        if inherited is not None and modal is None:
            subject = inherited.subject_text
            flags.append("inherited_list_stem")
        else:
            subject = self._subject_text(text, subject_start, modal_start)
            if subject is None and inherited is not None:
                subject = inherited.subject_text
                flags.append("inherited_subject")
                trace.append("subject:inherited from previous clause")

        component, state = self._split_subject(subject)
        if subject and _PRONOUN_SUBJECT.match(subject):
            flags.append("unclear_reference")
        if component is None and state is None:
            flags.append("missing_component")

        action = self._action(text, modal_end, min(first_comparator, region_end))
        if state is None:
            state = action

        if _VAGUE.search(clause):
            flags.append("vague_term")
        if _TBD.search(clause):
            flags.append("tbd_value")
        if _UNCLEAR_REF.search(clause):
            flags.append("unclear_reference")
        self._threshold_flags(constraints, flags)

        requirement_type = self._type(clause, constraints)
        source_label = None
        block_prefix = _SOURCE_LABEL.match(segment.text)
        if block_prefix:
            source_label = block_prefix.group(1) or block_prefix.group(2)

        return Requirement(
            requirement_id=self._new_id(), document_id=self.document_id, source_sha256=self.sha256, span_id=span_id,
            source_label=source_label, requirement_type=requirement_type, component=component, action_or_state=state,
            negated=negated, condition=condition_text,
            exception=text[exception_span[0]:exception_span[1]] if exception_span else None,
            constraints=constraints, evidence=self._evidence(block, self.section, start, end),
            quality_flags=sorted(set(flags)), trace=trace, method=BASELINE_VERSION,
        )

    @staticmethod
    def _split_subject(subject: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        if not subject:
            return None, None
        of_form = _PARAM_OF_COMPONENT.match(subject)
        if of_form and of_form.group("param").split()[-1].lower() in _PARAMETER_NOUNS:
            return of_form.group("comp"), _ARTICLE.sub("", of_form.group("param"))
        words = subject.split()
        if len(words) > 1 and words[-1].lower() in _PARAMETER_NOUNS and " of " not in subject:
            return " ".join(words[:-1]), subject
        return subject, None

    @staticmethod
    def _action(text: str, modal_end: int, stop: int) -> Optional[str]:
        start, end = _trim(text, modal_end, stop, ".,;:")
        chunk = text[start:end]
        trailing = re.compile(r"\s+(?:for|to|at|of|with|by|a|an|the|be|have|has|from|than|in)$", re.I)
        while True:
            shorter = trailing.sub("", chunk)
            if shorter == chunk:
                break
            chunk = shorter
        if chunk.lower() in {"be", "have", "not", ""}:
            return None
        return chunk

    @staticmethod
    def _type(clause: str, constraints: list[Constraint]) -> str:
        if _SAFETY.search(clause):
            return "safety"
        if _INTERFACE.search(clause):
            return "interface"
        if _ENVIRONMENT.search(clause):
            return "environmental"
        return "performance" if constraints else "functional"

    @staticmethod
    def _threshold_flags(constraints: list[Constraint], flags: list[str]) -> None:
        dims = {dimension(c.unit) for c in constraints if c.unit}
        if len(dims) > 1:
            flags.append("mixed_obligation")
        lower = [c.value for c in constraints if c.operator in (">=", ">") and c.value is not None]
        upper = [c.value for c in constraints if c.operator in ("<=", "<") and c.value is not None]
        units = {c.unit for c in constraints}
        if lower and upper and len(units) == 1 and max(lower) > min(upper):
            flags.append("conflicting_threshold")

    def _constraints(self, text: str, modal_start: int, start: int, end: int, condition: Optional[str],
                     flags: list[str], trace: list[str]) -> tuple[list[Constraint], int]:
        """Return the constraints and the position where the first limit expression begins."""
        found: list[Constraint] = []
        taken: list[tuple[int, int]] = []
        region = text[start:end]

        def free(a: int, b: int) -> bool:
            return all(b <= x or a >= y for x, y in taken)

        def add(s: int, e: int, operator: Optional[str], number: str, unit_surface: Optional[str], tolerance: Optional[float] = None) -> None:
            value, decimal_comma = parse_number(number)
            if decimal_comma:
                flags.append("decimal_comma")
            unit = canonical_unit(unit_surface)
            if unit is None:
                flags.append("undefined_unit")
            found.append(Constraint(parameter=self._parameter(unit, None, flags), operator=operator, value=value,
                                    tolerance=tolerance, unit=unit, condition=condition, surface_text=text[s:e], start_char=s, end_char=e))

        for pattern, name in ((_TOLERANCE, "tolerance"),):
            for m in pattern.finditer(region):
                s, e = start + m.start(), start + m.end()
                if free(s, e):
                    taken.append((s, e))
                    tolerance, _ = parse_number(m.group("b"))
                    add(s, e, "=", m.group("a"), m.group("ub"), tolerance)
                    trace.append("constraint:tolerance ±")

        for pattern, name in ((_RANGE_BETWEEN, "between"), (_RANGE_DASH, "range")):
            for m in pattern.finditer(region):
                s, e = start + m.start(), start + m.end()
                if free(s, e):
                    taken.append((s, e))
                    add(s, e, ">=", m.group("a"), m.group("ua") or m.group("ub"))
                    add(s, e, "<=", m.group("b"), m.group("ub"))
                    trace.append(f"constraint:{name} → two bounds")

        for m in _COMPARATOR_RE.finditer(region):
            s, e = start + m.start(), start + m.end()
            if not free(s, e):
                continue
            word = m.group("word")
            if word:
                normalized = re.sub(r"\s+", " ", word.lower())
                operator = next(op for pat, op in _COMPARATORS if re.fullmatch(pat, normalized, re.I))
            else:
                normalized = m.group("sym")
                operator = dict(_SYMBOLS)[normalized]
            # The search starts at the modal so that the "not" in "shall not exceed" counts.
            before = text[modal_start:s]
            negation = _NEGATION_BEFORE.search(before)
            surface_start = s
            if negation and word:
                if operator in _FLIP:
                    flipped = _FLIP[operator]
                    trace.append(f"polarity:{negation.group(1).lower()} + {normalized} → {flipped}")
                    operator = flipped
                else:
                    trace.append("polarity:negated equality is not a single threshold")
                    flags.append("operator_not_stated")
                    operator = None
                surface_start = modal_start + negation.start()
            else:
                trace.append(f"operator:{normalized} → {operator}")
            # Wording such as "no fewer than" sits after the modal and belongs to the limit, not the action.
            taken.append((max(surface_start, start), e))
            add(surface_start, e, operator, m.group("num"), m.group("unit"))

        for m in _BARE_EQUAL.finditer(region):
            s, e = start + m.start(), start + m.end()
            if free(s, e):
                taken.append((s, e))
                add(s, e, "=", m.group("num"), m.group("unit"))
                trace.append("operator:be <value> → =")

        for m in _BARE_QUANTITY.finditer(region):
            s, e = start + m.start(), start + m.end()
            if free(s, e):
                taken.append((s, e))
                add(s, e, None, m.group("num"), m.group("unit"))
                flags.append("operator_not_stated")
                trace.append("constraint:quantity without comparator")

        found.sort(key=lambda c: (c.start_char, c.operator != ">="))
        return found, min((a for a, _ in taken), default=end)


def extract(blocks: list[Block], document_id: str, sha256: str) -> tuple[list[Passage], list[Requirement]]:
    return Extractor(document_id, sha256).run(blocks)
