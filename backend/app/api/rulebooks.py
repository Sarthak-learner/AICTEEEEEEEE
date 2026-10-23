"""Rulebook management API: versioning, publishing, rule YAML upload."""
from __future__ import annotations
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import Rulebook, RulebookVersion, Rule, User
from app.auth import require_roles
from app.engine.loader import load_rule_from_yaml
from app.services.audit import record_event
import yaml
import tempfile
import os

router = APIRouter(prefix="/api/v1/rulebooks", tags=["rulebooks"])


class CreateRulebookRequest(BaseModel):
    name: str
    authority: str
    academic_year: str
    source_document: Optional[str] = None


@router.post("", status_code=201)
def create_rulebook(
    req: CreateRulebookRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CURATOR", "SYSTEM_ADMIN")),
):
    rb = Rulebook(
        name=req.name,
        authority=req.authority,
        academic_year=req.academic_year,
        source_document=req.source_document,
    )
    db.add(rb)
    db.flush()

    version = RulebookVersion(
        rulebook_id=rb.id,
        version_label=f"{req.academic_year}-v1",
        status="DRAFT",
    )
    db.add(version)
    db.flush()

    record_event(db, "RULEBOOK_CREATED", actor_id=current_user.id,
                 object_type="rulebook", object_id=rb.id)
    db.commit()
    return {"rulebook_id": rb.id, "version_id": version.id}


@router.get("")
def list_rulebooks(db: Session = Depends(get_db), current_user: User = Depends(require_roles(
    "CURATOR", "SYSTEM_ADMIN", "SCRUTINY_OFFICER", "SENIOR_REVIEWER"
))):
    rbs = db.query(Rulebook).all()
    result = []
    for rb in rbs:
        versions = db.query(RulebookVersion).filter(RulebookVersion.rulebook_id == rb.id).all()
        result.append({
            "id": rb.id, "name": rb.name, "academic_year": rb.academic_year,
            "versions": [{"id": v.id, "label": v.version_label, "status": v.status} for v in versions]
        })
    return result


@router.post("/{rulebook_id}/versions/{version_id}/rules", status_code=201)
async def upload_rule(
    rulebook_id: str,
    version_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CURATOR", "SYSTEM_ADMIN")),
):
    """Upload a YAML rule file and add it to a DRAFT rulebook version."""
    rb_version = db.query(RulebookVersion).filter(
        RulebookVersion.id == version_id,
        RulebookVersion.rulebook_id == rulebook_id,
        RulebookVersion.status == "DRAFT",
    ).first()
    if not rb_version:
        raise HTTPException(404, "Draft rulebook version not found")

    content = await file.read()
    try:
        rule_def = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML: {e}")

    # Validate schema
    from app.engine.loader import RULE_SCHEMA
    import jsonschema
    try:
        jsonschema.validate(rule_def, RULE_SCHEMA)
    except jsonschema.ValidationError as e:
        raise HTTPException(400, f"Rule validation error: {e.message}")

    # Check for duplicate rule_key
    existing = db.query(Rule).filter(
        Rule.rulebook_version_id == version_id,
        Rule.rule_key == rule_def["rule_key"],
    ).first()
    if existing:
        raise HTTPException(409, f"Rule {rule_def['rule_key']} already exists in this version")

    rule = Rule(
        rulebook_version_id=version_id,
        rule_key=rule_def["rule_key"],
        title=rule_def["title"],
        clause_ref=rule_def.get("clause_ref"),
        source_page=rule_def.get("source_page"),
        severity=rule_def["severity"],
        applicability=rule_def.get("applicability"),
        definition=rule_def,
        verified=rule_def.get("verified", False),
    )
    db.add(rule)

    record_event(db, "RULE_ADDED", actor_id=current_user.id,
                 object_type="rule", object_id=rule_def["rule_key"],
                 payload={"rulebook_version_id": version_id})
    db.commit()
    return {"rule_id": rule.id, "rule_key": rule.rule_key, "verified": rule.verified}


@router.post("/{rulebook_id}/versions/{version_id}/publish")
def publish_rulebook_version(
    rulebook_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CURATOR", "SYSTEM_ADMIN")),
):
    rb_version = db.query(RulebookVersion).filter(
        RulebookVersion.id == version_id,
        RulebookVersion.rulebook_id == rulebook_id,
    ).first()
    if not rb_version:
        raise HTTPException(404, "Rulebook version not found")
    if rb_version.status not in ("DRAFT", "APPROVED"):
        raise HTTPException(400, f"Cannot publish from status {rb_version.status}")

    # Run all built-in rule tests before publishing
    rules = db.query(Rule).filter(Rule.rulebook_version_id == version_id).all()
    test_failures = []
    from app.engine.evaluator import run_rule_tests
    for rule in rules:
        results = run_rule_tests(rule.definition)
        failed = [r for r in results if not r["passed"]]
        if failed:
            test_failures.append({"rule_key": rule.rule_key, "failures": failed})

    if test_failures:
        raise HTTPException(400, {
            "detail": "Cannot publish: rule tests failed",
            "failures": test_failures,
        })

    rb_version.status = "PUBLISHED"
    rb_version.approved_by = current_user.id
    rb_version.published_at = datetime.utcnow()

    record_event(db, "RULEBOOK_PUBLISHED", actor_id=current_user.id,
                 object_type="rulebook_version", object_id=version_id)
    db.commit()
    return {"version_id": version_id, "status": "PUBLISHED"}


@router.get("/{rulebook_id}/versions/{version_id}/test")
def run_rulebook_tests(
    rulebook_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CURATOR", "SYSTEM_ADMIN")),
):
    """Run built-in tests for all rules in a version."""
    rules = db.query(Rule).filter(Rule.rulebook_version_id == version_id).all()
    from app.engine.evaluator import run_rule_tests
    all_results = {}
    for rule in rules:
        results = run_rule_tests(rule.definition)
        all_results[rule.rule_key] = results
    return all_results
