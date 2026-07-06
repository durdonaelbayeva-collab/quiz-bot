"""
Bulk question parser.

Format the admin pastes as plain text (one or many questions in one message):

    Ranglar nazariyasida asosiy ranglar nechta?
    A) 2
    B) 3*
    C) 4
    D) 5

    Chizmachilikda asosiy chizish asbobi?
    A) Chizg'ich*
    B) Qalam
    C) O'chirg'ich
    D) Sirkul

Rules:
  - Each question is separated from the next by a BLANK LINE.
  - Option lines start with a letter A-D (or a-d) followed by ')' or '.'.
  - Exactly ONE option per question must end with '*' -- that's the correct answer.
  - Everything above the first option line is treated as the question text.

The same parser is reused for text extracted from an uploaded PDF, so admins
can prepare questions in Word/PDF using this exact format and upload the file
directly instead of retyping everything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

OPTION_RE = re.compile(r"^\s*[A-Da-d][\)\.]\s*(.+)$")


@dataclass
class ParsedQuestion:
    text: str
    options: list[tuple[str, bool]]


@dataclass
class ParseResult:
    questions: list[ParsedQuestion] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # human-readable problems, with the offending block


def parse_bulk_text(raw_text: str) -> ParseResult:
    """Parses a whole pasted/extracted text blob into ParsedQuestion objects."""
    result = ParseResult()

    # Split into blocks on blank lines (allow Windows line endings too)
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", normalized) if b.strip()]

    for block in blocks:
        parsed = _parse_block(block)
        if parsed is None:
            result.errors.append(block[:200])
        else:
            result.questions.append(parsed)

    return result


def _parse_block(block: str) -> ParsedQuestion | None:
    lines = [l.strip() for l in block.split("\n") if l.strip()]
    question_lines: list[str] = []
    options: list[tuple[str, bool]] = []

    for line in lines:
        match = OPTION_RE.match(line)
        if match:
            text = match.group(1).strip()
            is_correct = text.endswith("*")
            if is_correct:
                text = text[:-1].strip()
            options.append((text, is_correct))
        elif not options:
            # still in the question-text portion (before any option line appeared)
            question_lines.append(line)
        # lines appearing after options started but not matching option pattern are ignored

    question_text = " ".join(question_lines).strip()
    question_text = re.sub(r"^(Savol\s*[:\.]?\s*)", "", question_text, flags=re.IGNORECASE)

    if not question_text or len(options) < 2:
        return None
    correct_count = sum(1 for _, is_correct in options if is_correct)
    if correct_count != 1:
        return None

    return ParsedQuestion(text=question_text, options=options)


def extract_text_from_pdf(filepath: str) -> str:
    """Extracts all text from a PDF, page by page, joined with blank lines
    so page breaks don't accidentally merge two separate questions."""
    import pdfplumber

    pages_text = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages_text.append(text)
    return "\n\n".join(pages_text)
