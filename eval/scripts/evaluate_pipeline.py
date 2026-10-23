"""Evaluation and benchmark script for SIH26261 pipeline accuracy."""
import json
import sys
from pathlib import Path

# Add backend to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.database import SessionLocal, Base, engine
from app.models import ApplicationVersion, ExtractedField, VerificationRun, VerificationResult


def run_evaluation():
    labels_file = Path(__file__).parent.parent / "labels" / "demo_ground_truth.json"
    if not labels_file.exists():
        print(f"Error: {labels_file} not found")
        return

    with open(labels_file, "r", encoding="utf-8") as f:
        gt = json.load(f)

    db = SessionLocal()
    try:
        # Find latest completed application version
        version = db.query(ApplicationVersion).order_by(ApplicationVersion.submitted_at.desc()).first()
        if not version:
            print("No application versions found in database to evaluate.")
            return

        print(f"==================================================")
        print(f"SIH26261 ACCURACY & BENCHMARK EVALUATION")
        print(f"Application Version ID: {version.id}")
        print(f"==================================================")

        # 1. Field Extraction Accuracy
        fields = db.query(ExtractedField).filter(ExtractedField.version_id == version.id).all()
        extracted_map = {}
        for f in fields:
            if f.normalised_value and "value" in f.normalised_value:
                extracted_map[f.field_key] = f.normalised_value["value"]

        gt_fields = gt.get("ground_truth_fields", {})
        correct_fields = 0
        total_gt = len(gt_fields)

        print("\n--- Field Extraction Metrics ---")
        for key, expected_val in gt_fields.items():
            actual_val = extracted_map.get(key)
            match = False
            if actual_val is not None:
                if isinstance(expected_val, float) and isinstance(actual_val, (int, float)):
                    match = abs(float(actual_val) - expected_val) < 0.05
                elif isinstance(expected_val, str) and isinstance(actual_val, str):
                    from app.pipeline.normalise import normalise_name
                    match = normalise_name(expected_val) == normalise_name(actual_val) or normalise_name(expected_val) in normalise_name(actual_val)
                else:
                    match = str(actual_val) == str(expected_val)

            status = "MATCH" if match else "MISMATCH"
            if match:
                correct_fields += 1
            print(f"  {key:25s}: Expected={str(expected_val):15s} Actual={str(actual_val):15s} [{status}]")

        field_acc = (correct_fields / total_gt * 100) if total_gt > 0 else 0
        print(f"\nField Extraction Accuracy: {field_acc:.1f}% ({correct_fields}/{total_gt})")

        # 2. Rule Verdict Accuracy
        latest_run = db.query(VerificationRun).filter(
            VerificationRun.version_id == version.id
        ).order_by(VerificationRun.started_at.desc()).first()

        if latest_run:
            results = db.query(VerificationResult).filter(VerificationResult.run_id == latest_run.id).all()
            expected_verdicts = gt.get("expected_verdicts", {})
            correct_rules = 0
            total_rules = len(expected_verdicts)

            print("\n--- Compliance Engine Accuracy ---")
            for r in results:
                rule_key = r.rule.rule_key if r.rule else "Unknown"
                exp = expected_verdicts.get(rule_key)
                match = (r.status == exp)
                if match:
                    correct_rules += 1
                status = "PASS" if match else "FAIL"
                print(f"  {rule_key:25s}: Expected={str(exp):8s} Got={str(r.status):8s} [{status}]")

            rule_acc = (correct_rules / total_rules * 100) if total_rules > 0 else 0
            print(f"\nRule Decision Accuracy: {rule_acc:.1f}% ({correct_rules}/{total_rules})")

        print("\n==================================================")
        print("Evaluation complete.")
        print("==================================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_evaluation()
