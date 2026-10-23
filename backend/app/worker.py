"""Background worker (RQ) that processes document pipeline jobs.

Jobs:
- process_document(document_id): OCR, classify, extract fields
- run_verification(version_id, rulebook_version_id): rule engine + consistency + integrity
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Document, Page, ExtractedField, ApplicationVersion,
    VerificationRun, VerificationResult, EvidenceRef,
    ConsistencyEdge, IntegrityFinding, ScanStatus,
    Rule, RulebookVersion, AuditEvent,
)
from app.pipeline.ocr import extract_text_from_pdf, PageOCRResult
from app.pipeline.classify import classify_document
from app.pipeline.extract import extract_fields
from app.consistency import run_consistency_checks, ConsistencyNode
from app.integrity import run_all_integrity_checks
from app.engine.evaluator import evaluate_all_rules, FactValue, ENGINE_VERSION
from app.services.storage import retrieve_path
from app.services.audit import record_event

logger = logging.getLogger(__name__)


def get_db() -> Session:
    return SessionLocal()


def process_document(document_id: str):
    """OCR, classify, extract fields from a document. Called by RQ worker."""
    db = get_db()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(f"Document {document_id} not found")
            return

        doc.scan_status = ScanStatus.PROCESSING
        db.commit()

        pdf_path = retrieve_path(doc.storage_key)

        # OCR
        try:
            page_results = extract_text_from_pdf(pdf_path)
        except Exception as e:
            logger.exception(f"OCR failed for document {document_id}: {e}")
            doc.scan_status = ScanStatus.FAILED
            db.commit()
            return

        all_tokens = []
        for pr in page_results:
            # Save page record
            page = Page(
                document_id=doc.id,
                page_no=pr.page_no,
                ocr_engine=pr.ocr_engine,
                dpi=300 if pr.ocr_engine == "tesseract" else None,
            )

            # Classify page/document
            cls_result = classify_document(pr.tokens)
            page.page_class = cls_result.doc_type
            page.class_confidence = cls_result.confidence
            db.add(page)
            db.flush()

            # Extract fields from this page
            effective_doc_type = doc.doc_type if doc.doc_type != "AUTO" else cls_result.doc_type
            candidates = extract_fields(effective_doc_type, pr.tokens, pr.page_no)

            for cand in candidates:
                norm_val = None
                if cand.normalised_value is not None:
                    if hasattr(cand.normalised_value, 'value'):
                        norm_val = {
                            "value": cand.normalised_value.value,
                            "unit": cand.normalised_value.unit,
                            "valid": cand.normalised_value.valid,
                        }
                    else:
                        norm_val = {"value": cand.normalised_value}

                field = ExtractedField(
                    version_id=doc.version_id,
                    field_key=cand.field_key,
                    raw_value=cand.raw_value,
                    normalised_value=norm_val,
                    unit=cand.unit if hasattr(cand, 'unit') else (norm_val or {}).get("unit"),
                    confidence=cand.confidence,
                    page_id=page.id,
                    bbox=cand.bbox,
                    extractor=cand.extractor,
                    status=cand.status,
                    fail_reason=cand.fail_reason,
                )
                db.add(field)

            all_tokens.extend(pr.tokens)

        # Integrity checks
        integrity_results = run_all_integrity_checks(pdf_path)
        for ir in integrity_results:
            finding = IntegrityFinding(
                document_id=doc.id,
                check_type=ir.check_type,
                indicator=ir.indicator,
                severity=ir.severity,
                detail=ir.detail,
                is_proof=ir.is_proof,
            )
            db.add(finding)

        doc.scan_status = ScanStatus.DONE
        db.commit()

        record_event(db, "DOCUMENT_PROCESSED", object_type="document", object_id=doc.id)
        db.commit()

        logger.info(f"Document {document_id} processed successfully")

    except Exception as e:
        logger.exception(f"Worker error processing document {document_id}: {e}")
        try:
            doc.scan_status = ScanStatus.FAILED
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


def run_verification(version_id: str, rulebook_version_id: str, run_id: Optional[str] = None):
    """Run rule engine + consistency checks for an application version."""
    db = get_db()
    try:
        version = db.query(ApplicationVersion).filter(ApplicationVersion.id == version_id).first()
        if not version:
            logger.error(f"ApplicationVersion {version_id} not found")
            return

        # Reuse existing run if provided, otherwise create one
        run = None
        if run_id:
            run = db.query(VerificationRun).filter(VerificationRun.id == run_id).first()
        if run:
            run.engine_version = ENGINE_VERSION
            run.status = "RUNNING"
            run.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            run = VerificationRun(
                version_id=version_id,
                rulebook_version_id=rulebook_version_id,
                engine_version=ENGINE_VERSION,
                status="RUNNING",
                started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )

            db.add(run)
        db.flush()

        # Load rules from DB
        rb_version = db.query(RulebookVersion).filter(RulebookVersion.id == rulebook_version_id).first()
        if not rb_version:
            run.status = "FAILED"
            db.commit()
            return

        rules_db = db.query(Rule).filter(Rule.rulebook_version_id == rulebook_version_id).all()
        rule_defs = [r.definition for r in rules_db]
        rule_db_ids = {r.definition["rule_key"]: r.id for r in rules_db}

        # Build facts from extracted fields
        fields = db.query(ExtractedField).filter(
            ExtractedField.version_id == version_id
        ).all()

        facts: dict[str, FactValue] = {}
        for f in fields:
            if f.status == "INDETERMINATE":
                facts[f.field_key] = FactValue(
                    value=None,
                    confidence=f.confidence or 0.0,
                    field_id=f.id,
                )
            elif f.normalised_value and f.normalised_value.get("valid", True):
                facts[f.field_key] = FactValue(
                    value=f.normalised_value.get("value"),
                    confidence=f.confidence or 1.0,
                    field_id=f.id,
                    page_id=f.page_id,
                    bbox=f.bbox,
                    unit=f.normalised_value.get("unit"),
                )

        # Add document completeness fact
        docs = db.query(Document).filter(Document.version_id == version_id).all()
        doc_types = [d.doc_type for d in docs if d.doc_type != "AUTO"]
        facts["submitted_doc_types"] = FactValue(
            value=doc_types, confidence=1.0
        )

        # Run rules
        findings = evaluate_all_rules(rule_defs, facts, rule_db_ids)

        for finding in findings:
            result = VerificationResult(
                run_id=run.id,
                rule_id=finding.rule_id,
                status=finding.status,
                required_value=finding.required_value,
                observed_value=finding.observed_value,
                explanation=finding.explanation,
                confidence=finding.confidence,
            )
            db.add(result)
            db.flush()

            # Add evidence refs
            for field_id in finding.evidence_field_ids:
                ev_ref = EvidenceRef(
                    result_id=result.id,
                    field_id=field_id,
                )
                db.add(ev_ref)

        # Consistency checks
        nodes = []
        for f in fields:
            if f.status != "INDETERMINATE" and f.normalised_value:
                doc = next((d for d in docs if any(
                    p.id == f.page_id for p in d.pages
                )), None) if f.page_id else None
                nodes.append(ConsistencyNode(
                    field_id=f.id,
                    field_key=f.field_key,
                    value=f.normalised_value.get("value") if f.normalised_value else None,
                    unit=f.unit,
                    doc_type=doc.doc_type if doc else "UNKNOWN",
                    document_id=doc.id if doc else "",
                    page_no=None,
                    bbox=f.bbox,
                ))

        consistency_findings = run_consistency_checks(nodes)
        for cf in consistency_findings:
            edge = ConsistencyEdge(
                version_id=version_id,
                field_a_id=cf.field_a_id,
                field_b_id=cf.field_b_id,
                relation=cf.relation,
                similarity=cf.similarity,
                status=cf.status,
                detail=cf.detail,
                severity=cf.severity,
            )
            db.add(edge)

        run.status = "DONE"
        run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()


        record_event(db, "VERIFICATION_COMPLETED", object_type="verification_run", object_id=run.id,
                     payload={"findings_count": len(findings), "consistency_count": len(consistency_findings)})
        db.commit()

        logger.info(f"Verification run {run.id} completed: {len(findings)} rule findings, {len(consistency_findings)} consistency edges")

    except Exception as e:
        logger.exception(f"Verification error: {e}")
        try:
            run.status = "FAILED"
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ─── RQ worker entrypoint ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import redis
    from rq import Worker, Queue
    from app.config import get_settings

    settings = get_settings()
    conn = redis.from_url(settings.REDIS_URL)
    queues = [Queue("sih_pipeline", connection=conn)]
    worker = Worker(queues, connection=conn)
    worker.work()
