"""Regulatory rule proposer with verbatim quotation validation.

Enforces Blueprint.md section 13 safety rules:
1. Verbatim quote check: Quoted evidence sentence must be found verbatim in the clause.
2. Numeric grounding: Every numeric threshold in the draft must appear in the quoted text.
3. Proposals are drafts with verified=false, requiring curator approval.
"""
from __future__ import annotations
import re
import json
from dataclasses import dataclass
from typing import Optional, Any
from rag.segment import ClauseSegment


@dataclass
class ProposalValidationResult:
    valid: bool
    errors: list[str]
    draft_rule: Optional[dict] = None


def validate_rule_proposal(clause: ClauseSegment, draft_rule: dict) -> ProposalValidationResult:
    """Validate that draft rule is strictly grounded in the official clause text."""
    errors = []

    # Check rule structure
    required_keys = ["rule_key", "title", "severity", "check", "quoted_source"]
    for k in required_keys:
        if k not in draft_rule:
            errors.append(f"Missing required key in proposal: '{k}'")

    if errors:
        return ProposalValidationResult(valid=False, errors=errors)

    quoted = draft_rule.get("quoted_source", "").strip()
    if not quoted:
        errors.append("Proposal must include 'quoted_source' from the official clause.")
        return ProposalValidationResult(valid=False, errors=errors)

    # 1. Verbatim quote validation
    clause_clean = " ".join(clause.content.lower().split())
    quote_clean = " ".join(quoted.lower().split())

    if quote_clean not in clause_clean:
        errors.append(f"Quoted source text is not found verbatim in clause {clause.clause_id}.")

    # 2. Numeric grounding check
    check_def = draft_rule.get("check", {})
    params = check_def.get("params", {})
    for p_name, p_val in params.items():
        if isinstance(p_val, (int, float)):
            num_str = str(p_val).rstrip('0').rstrip('.') if '.' in str(p_val) else str(p_val)
            # Find if this number or its integer representation is in quoted text
            if num_str not in quoted and str(int(p_val) if isinstance(p_val, (int, float)) else "") not in quoted:
                # Also check common fractions (e.g. 1:15 or 15 or 0.0667)
                if not any(token in quoted for token in [num_str, f"1:{int(1/p_val)}" if p_val > 0 and p_val < 1 else ""]):
                    errors.append(f"Numeric parameter '{p_name}' ({p_val}) does not appear in quoted text.")

    # 3. Always unverified draft
    draft_rule["verified"] = False
    draft_rule["clause_ref"] = f"Clause {clause.clause_id}: {clause.title}"

    return ProposalValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        draft_rule=draft_rule if len(errors) == 0 else None
    )


class RuleProposer:
    """Interface for LLM or pattern-based rule proposals."""

    def propose_from_clause(self, clause: ClauseSegment) -> ProposalValidationResult:
        """Extract rule draft from clause text."""
        # Detect common patterns for offline/deterministic proposals
        text = clause.content.lower()

        # Faculty ratio pattern
        ratio_match = re.search(r"faculty[:\s]+student[:\s]+ratio[:\s]+(?:of\s+)?1\s*:\s*(\d+)", text)
        if ratio_match:
            denom = float(ratio_match.group(1))
            val = round(1.0 / denom, 4)
            draft = {
                "rule_key": f"FAC_RATIO_AUTO_{clause.clause_id.replace('.', '_')}",
                "title": f"Faculty Ratio ({clause.title})",
                "severity": "CRITICAL",
                "quoted_source": ratio_match.group(0),
                "inputs": {
                    "total_faculty": {"type": "int", "min_confidence": 0.85},
                    "sanctioned_intake_total": {"type": "int", "min_confidence": 0.85},
                },
                "check": {
                    "fn": "ratio_at_least",
                    "params": {
                        "numerator": "total_faculty",
                        "denominator": "sanctioned_intake_total",
                        "minimum": val,
                    }
                }
            }
            return validate_rule_proposal(clause, draft)

        return ProposalValidationResult(
            valid=False,
            errors=[f"No supported rule pattern could be deterministically extracted from clause {clause.clause_id}."]
        )
