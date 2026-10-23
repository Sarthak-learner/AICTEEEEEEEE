"""Seed verification run for demo application using synthetic documents.

Processes all 6 synthetic PDFs through:
- Ingestion & storage
- OCR & classification
- Deterministic extraction
- Rule evaluation
- Cross-document consistency graph
"""
import os
import sys
from pathlib import Path

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal
from app.models import (
    ApplicationVersion, Document, VerificationRun, ScanStatus
)
from app.pipeline.ingest import validate_and_store
from app.worker import process_document, run_verification

def main():
    db = SessionLocal()
    version = db.query(ApplicationVersion).filter(ApplicationVersion.id == "appv-demo-0042-v1").first()
    if not version:
        print("Demo version appv-demo-0042-v1 not found. Run seed_db.py first.")
        return

    docs_dir = Path(__file__).parent.parent.parent / "data" / "synthetic" / "output"
    if not docs_dir.exists():
        print(f"Directory {docs_dir} not found.")
        return

    doc_mapping = {
        "01_APPLICATION_FORM.pdf": "APPLICATION_FORM",
        "02_FACULTY_LIST.pdf": "FACULTY_LIST",
        "03_FINANCIAL_STATEMENT.pdf": "FINANCIAL_STATEMENT",
        "04_LAND_DEED.pdf": "LAND_DEED",
        "05_BUILDING_PLAN.pdf": "BUILDING_PLAN",
        "06_FACULTY_AFFIDAVIT.pdf": "FACULTY_AFFIDAVIT",
    }

    print("Checking / ingesting documents for demo application...")
    doc_ids = []
    for filename, doc_type in doc_mapping.items():
        filepath = docs_dir / filename
        if not filepath.exists():
            print(f"  Missing {filename}")
            continue

        existing_doc = db.query(Document).filter(
            Document.version_id == version.id,
            Document.original_name == filename
        ).first()

        if not existing_doc:
            with open(filepath, "rb") as f:
                bytes_data = f.read()

            stored = validate_and_store(bytes_data, filename)
            doc = Document(
                version_id=version.id,
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
            print(f"  Uploaded: {filename} ({doc_type}) -> {doc.id}")
        else:
            doc_ids.append(existing_doc.id)
            print(f"  Existing: {filename} ({doc_type}) -> {existing_doc.id}")

    db.commit()

    # Process documents through OCR & extraction
    print("\nProcessing documents through OCR & field extraction...")
    for doc_id in doc_ids:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc and doc.scan_status != ScanStatus.DONE:
            print(f"  Processing {doc.original_name}...")
            process_document(doc_id)
        else:
            print(f"  Already processed {doc.original_name if doc else doc_id}")

    # Check for existing run
    run = db.query(VerificationRun).filter(
        VerificationRun.version_id == version.id,
        VerificationRun.status == "DONE"
    ).first()

    if not run:
        print("\nRunning verification and cross-document consistency checks...")
        new_run = VerificationRun(
            version_id=version.id,
            rulebook_version_id=version.rulebook_version_id,
            status="QUEUED"
        )
        db.add(new_run)
        db.commit()

        run_verification(version.id, version.rulebook_version_id, new_run.id)
        db.refresh(new_run)
        print(f"Verification complete: run_id={new_run.id}, status={new_run.status}")
    else:
        print(f"\nVerification run already completed: run_id={run.id}")

    db.close()
    print("Demo pipeline seeding complete!")

if __name__ == "__main__":
    main()
