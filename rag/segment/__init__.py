"""Regulatory text segmentation for AICTE Approval Process Handbook (APH).

Segments official handbook text into identifiable clauses with citations.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ClauseSegment:
    clause_id: str
    title: str
    content: str
    academic_year: str = "2026-27"
    page_no: Optional[int] = None


# Pattern matching clauses like "Clause 2.1.4", "Section 4.3", "Rule 7.1"
CLAUSE_HEADING_PATTERN = re.compile(
    r"(?:(?:Clause|Section|Rule|Appendix|Annexure)\s+([\d\w\.]+))\s*[:\-\.]?\s*(.*?)(?=\n)",
    re.IGNORECASE
)


def segment_handbook_text(text: str, academic_year: str = "2026-27") -> list[ClauseSegment]:
    """Segment raw handbook text into structured clause objects."""
    segments = []
    lines = text.splitlines()

    current_id = "General"
    current_title = "Introductory Provisions"
    current_lines: list[str] = []

    for line in lines:
        match = CLAUSE_HEADING_PATTERN.match(line.strip())
        if match:
            # Flush previous clause
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    segments.append(ClauseSegment(
                        clause_id=current_id,
                        title=current_title,
                        content=content,
                        academic_year=academic_year
                    ))
            current_id = match.group(1).strip()
            current_title = match.group(2).strip() or f"Section {current_id}"
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            segments.append(ClauseSegment(
                clause_id=current_id,
                title=current_title,
                content=content,
                academic_year=academic_year
            ))

    return segments
