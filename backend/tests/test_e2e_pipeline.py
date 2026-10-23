"""End-to-end verification pipeline test using synthetic demo documents."""
import os
import pytest
from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.models import (
    Institution, User, Application, ApplicationVersion, Document,
    Rulebook, RulebookVersion, Rule, VerificationRun, VerificationResult,
    ExtractedField, ScanStatus
)
from app.pipeline.ingest import validate_and_store
from app.worker import process_document, run_verification
from app.reports import render_json_report
from app.engine.loader import load_rulebook_from_dir


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # Create demo institution & user if not present
    inst = db.query(Institution).filter(Institution.id == "test-inst-1").first()
    if not inst:
        inst = Institution(id="test-inst-1", name="Sunrise Institute of Technology, Demo City")
        db.add(inst)
    
    # Load and publish rulebook
    rb = db.query(Rulebook).filter(Rulebook.id == "test-rb-1").first()
    if not rb:
        rb = Rulebook(id="test-rb-1", name="AICTE APH 2026-27", academic_year="2026-27")
        db.add(rb)
        db.flush()

    rbv = db.query(RulebookVersion).filter(RulebookVersion.id == "test-rbv-1").first()
    if not rbv:
        rbv = RulebookVersion(id="test-rbv-1", rulebook_id=rb.id, version_label="TEST-v1", status="PUBLISHED")
        db.add(rbv)
        db.flush()

        rules_dir = Path(__file__).parent.parent.parent / "rulebooks" / "2026-27"
        rules, _ = load_rulebook_from_dir(rules_dir)
        for r_def in rules:
            rule = Rule(
                rulebook_version_id=rbv.id,
                rule_key=r_def["rule_key"],
                title=r_def["title"],
                severity=r_def["severity"],
                definition=r_def,
            )
            db.add(rule)

    db.commit()
    yield db
    db.close()


def test_e2e_document_pipeline_and_verification(setup_db):
    db = setup_db
    docs_dir = Path(__file__).parent.parent.parent / "data" / "synthetic" / "output"
    assert docs_dir.exists(), "Synthetic demo documents must be generated first"

    # Create application & version
    app = Application(
        institution_id="test-inst-1",
        academic_year="2026-27",
        program_type="UG Engineering",
        category="Extension of Approval",
        status="DRAFT"
    )
    db.add(app)
    db.flush()

    v1 = ApplicationVersion(
        application_id=app.id,
        version_no=1,
        rulebook_version_id="test-rbv-1",
        status="SUBMITTED"
    )
    db.add(v1)
    db.flush()

    # Upload and process documents
    doc_mapping = {
        "01_APPLICATION_FORM.pdf": "APPLICATION_FORM",
        "02_FACULTY_LIST.pdf": "FACULTY_LIST",
        "03_FINANCIAL_STATEMENT.pdf": "FINANCIAL_STATEMENT",
        "04_LAND_DEED.pdf": "LAND_DEED",
        "05_BUILDING_PLAN.pdf": "BUILDING_PLAN",
        "06_FACULTY_AFFIDAVIT.pdf": "FACULTY_AFFIDAVIT",
    }

    doc_ids = []
    for filename, doc_type in doc_mapping.items():
        filepath = docs_dir / filename
        assert filepath.exists(), f"File {filename} missing"
        with open(filepath, "rb") as f:
            bytes_data = f.read()

        stored = validate_and_store(bytes_data, filename)
        doc = Document(
            version_id=v1.id,
            doc_type=doc_type,
            original_name=filename,
            mime=stored["mime"],
            sha256=stored["sha256"],
            storage_key=stored["storage_key"],
            page_count=stored["page_count"],
            scan_status=ScanStatus.QUEUED,
        )
        db.add(doc)
        db.flush()
        doc_ids.append(doc.id)

    db.commit()

    # Process all documents through OCR and extraction
    for doc_id in doc_ids:
        process_document(doc_id)

    # Check extracted fields
    fields = db.query(ExtractedField).filter(ExtractedField.version_id == v1.id).all()
    assert len(fields) > 0, "Fields should be extracted from synthetic documents"
    field_keys = {f.field_key for f in fields}
    assert "sanctioned_intake_total" in field_keys
    assert "total_faculty" in field_keys

    # Create and run verification
    run = VerificationRun(
        version_id=v1.id,
        rulebook_version_id="test-rbv-1",
        status="QUEUED"
    )
    db.add(run)
    db.commit()

    run_verification(v1.id, "test-rbv-1", run.id)

    # Verify run completed
    db.refresh(run)
    assert run.status == "DONE"

    # Check findings
    results = db.query(VerificationResult).filter(VerificationResult.run_id == run.id).all()
    assert len(results) == 6, "All 6 rules must be evaluated"

    results_by_rule = {r.rule.rule_key: r for r in results}

    # Planted issue 1: 58 faculty / 1200 intake must FAIL
    assert results_by_rule["FAC_RATIO_UG_ENGG"].status == "FAIL"

    # Document completeness must PASS (all 6 uploaded)
    assert results_by_rule["DOC_COMPLETENESS"].status == "PASS"

    # Financial corpus (Rs. 6.00 Cr >= 5.0 Cr) must PASS
    assert results_by_rule["FIN_CORPUS_UG_ENGG"].status == "PASS"

    # Generate JSON report
    report = render_json_report(db, v1.id)
    assert report["overall_status"] == "FAIL"
    assert report["counts"]["FAIL"] >= 1
    assert report["counts"]["PASS"] >= 1

    # Generate PDF report
    from app.reports import render_pdf_report
    pdf_bytes = render_pdf_report(db, v1.id)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 500

