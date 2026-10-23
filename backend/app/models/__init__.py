"""SQLAlchemy ORM models for the SIH26261 compliance system.

Primary keys are UUIDs. Audit events are hash-chained and immutable.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, Enum,
    ForeignKey, UniqueConstraint, BigInteger, JSON, event, text
)
from sqlalchemy.orm import relationship
from app.database import Base, engine

# Use JSONB on PostgreSQL, fall back to JSON on SQLite / other dialects
if engine.dialect.name == "postgresql":
    try:
        from sqlalchemy.dialects.postgresql import JSONB
    except ImportError:
        JSONB = JSON
else:
    JSONB = JSON


def gen_uuid():
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─── Enums ────────────────────────────────────────────────────────────────────

import enum as pyenum


class UserRole(str, pyenum.Enum):
    INSTITUTION_ADMIN = "INSTITUTION_ADMIN"
    SCRUTINY_OFFICER = "SCRUTINY_OFFICER"
    SENIOR_REVIEWER = "SENIOR_REVIEWER"
    CURATOR = "CURATOR"
    AUDITOR = "AUDITOR"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class AppStatus(str, pyenum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    DEFICIENCY_ISSUED = "DEFICIENCY_ISSUED"
    RESUBMITTED = "RESUBMITTED"
    RECOMMENDED = "RECOMMENDED"
    REJECTED_RECOMMENDED = "REJECTED_RECOMMENDED"


class ScanStatus(str, pyenum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"


class FieldStatus(str, pyenum.Enum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"
    INDETERMINATE = "INDETERMINATE"


class RuleStatus(str, pyenum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Severity(str, pyenum.Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    ADVISORY = "ADVISORY"


class RulebookStatus(str, pyenum.Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


class ReviewAction(str, pyenum.Enum):
    CONFIRM = "CONFIRM"
    OVERRIDE = "OVERRIDE"
    REQUEST_CORRECTION = "REQUEST_CORRECTION"


class SignatureResult(str, pyenum.Enum):
    VALID_INTACT = "VALID_INTACT"
    VALID_UNTRUSTED_CHAIN = "VALID_UNTRUSTED_CHAIN"
    MODIFIED_AFTER_SIGNING = "MODIFIED_AFTER_SIGNING"
    INVALID = "INVALID"
    NO_SIGNATURE = "NO_SIGNATURE"
    REVOCATION_UNKNOWN = "REVOCATION_UNKNOWN"


# ─── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    officer_id = Column(String(50), unique=True, nullable=True, index=True)
    name = Column(String(200), nullable=False)
    email = Column(String(200), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(30), nullable=False)
    institution_id = Column(String(36), ForeignKey("institutions.id"), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    institution = relationship("Institution", back_populates="users")
    assigned_applications = relationship("Application", back_populates="assigned_officer")


class Institution(Base):
    __tablename__ = "institutions"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(500), nullable=False)
    aicte_id_text = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    type = Column(String(100), nullable=True)  # Private / Government / Aided

    users = relationship("User", back_populates="institution")
    applications = relationship("Application", back_populates="institution")


class Application(Base):
    __tablename__ = "applications"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    institution_id = Column(String(36), ForeignKey("institutions.id"), nullable=False)
    assigned_officer_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    academic_year = Column(String(20), nullable=False)
    program_type = Column(String(100), nullable=False)
    category = Column(String(100), nullable=False)
    current_version_no = Column(Integer, default=1)
    status = Column(String(40), default=AppStatus.DRAFT)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    institution = relationship("Institution", back_populates="applications")
    assigned_officer = relationship("User", back_populates="assigned_applications")
    versions = relationship("ApplicationVersion", back_populates="application", order_by="ApplicationVersion.version_no")


class ApplicationVersion(Base):
    __tablename__ = "application_versions"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    application_id = Column(String(36), ForeignKey("applications.id"), nullable=False)
    version_no = Column(Integer, nullable=False)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    rulebook_version_id = Column(String(36), ForeignKey("rulebook_versions.id"), nullable=True)
    status = Column(String(40), default="DRAFT")

    __table_args__ = (UniqueConstraint("application_id", "version_no"),)

    application = relationship("Application", back_populates="versions")
    documents = relationship("Document", back_populates="version")
    extracted_fields = relationship("ExtractedField", back_populates="version")
    verification_runs = relationship("VerificationRun", back_populates="version")


class Document(Base):
    __tablename__ = "documents"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    version_id = Column(String(36), ForeignKey("application_versions.id"), nullable=False)
    doc_type = Column(String(100), nullable=False)
    original_name = Column(String(500), nullable=False)
    mime = Column(String(100), nullable=True)
    sha256 = Column(String(64), nullable=False, index=True)
    storage_key = Column(String(500), nullable=False)
    page_count = Column(Integer, default=0)
    scan_status = Column(String(20), default=ScanStatus.QUEUED)
    created_at = Column(DateTime, default=utc_now)

    version = relationship("ApplicationVersion", back_populates="documents")
    pages = relationship("Page", back_populates="document")
    integrity_findings = relationship("IntegrityFinding", back_populates="document")


class Page(Base):
    __tablename__ = "pages"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    page_no = Column(Integer, nullable=False)
    page_class = Column(String(100), nullable=True)
    class_confidence = Column(Float, nullable=True)
    dpi = Column(Integer, nullable=True)
    ocr_engine = Column(String(50), nullable=True)  # native | tesseract

    document = relationship("Document", back_populates="pages")
    extracted_fields = relationship("ExtractedField", back_populates="page")


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    version_id = Column(String(36), ForeignKey("application_versions.id"), nullable=False)
    field_key = Column(String(100), nullable=False)
    raw_value = Column(Text, nullable=True)
    normalised_value = Column(JSONB, nullable=True)
    unit = Column(String(50), nullable=True)
    confidence = Column(Float, nullable=True)
    page_id = Column(String(36), ForeignKey("pages.id"), nullable=True)
    bbox = Column(JSONB, nullable=True)  # [x0, y0, x1, y1]
    extractor = Column(String(100), nullable=True)
    status = Column(String(20), default=FieldStatus.AUTO)
    fail_reason = Column(String(200), nullable=True)
    corrected_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    corrected_at = Column(DateTime, nullable=True)
    old_value = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    version = relationship("ApplicationVersion", back_populates="extracted_fields")
    page = relationship("Page", back_populates="extracted_fields")


class Rulebook(Base):
    __tablename__ = "rulebooks"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(200), nullable=False)
    authority = Column(String(200), nullable=True)
    academic_year = Column(String(20), nullable=False)
    source_document = Column(String(500), nullable=True)
    source_sha256 = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    versions = relationship("RulebookVersion", back_populates="rulebook")


class RulebookVersion(Base):
    __tablename__ = "rulebook_versions"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    rulebook_id = Column(String(36), ForeignKey("rulebooks.id"), nullable=False)
    version_label = Column(String(100), nullable=False)
    status = Column(String(20), default=RulebookStatus.DRAFT)
    approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    published_at = Column(DateTime, nullable=True)
    content_sha256 = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    rulebook = relationship("Rulebook", back_populates="versions")
    rules = relationship("Rule", back_populates="rulebook_version")


class Rule(Base):
    __tablename__ = "rules"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    rulebook_version_id = Column(String(36), ForeignKey("rulebook_versions.id"), nullable=False)
    rule_key = Column(String(100), nullable=False)
    title = Column(String(500), nullable=False)
    clause_ref = Column(String(500), nullable=True)
    source_page = Column(String(100), nullable=True)
    severity = Column(String(20), nullable=False)
    applicability = Column(JSONB, nullable=True)
    definition = Column(JSONB, nullable=False)  # full rule spec
    verified = Column(Boolean, default=False)

    rulebook_version = relationship("RulebookVersion", back_populates="rules")
    verification_results = relationship("VerificationResult", back_populates="rule")


class VerificationRun(Base):
    __tablename__ = "verification_runs"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    version_id = Column(String(36), ForeignKey("application_versions.id"), nullable=False)
    rulebook_version_id = Column(String(36), ForeignKey("rulebook_versions.id"), nullable=False)
    started_at = Column(DateTime, default=utc_now)
    finished_at = Column(DateTime, nullable=True)
    engine_version = Column(String(50), nullable=True)
    status = Column(String(20), default="RUNNING")

    version = relationship("ApplicationVersion", back_populates="verification_runs")
    results = relationship("VerificationResult", back_populates="run")


class VerificationResult(Base):
    __tablename__ = "verification_results"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    run_id = Column(String(36), ForeignKey("verification_runs.id"), nullable=False)
    rule_id = Column(String(36), ForeignKey("rules.id"), nullable=False)
    status = Column(String(20), nullable=False)
    required_value = Column(Text, nullable=True)
    observed_value = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)

    run = relationship("VerificationRun", back_populates="results")
    rule = relationship("Rule", back_populates="verification_results")
    evidence_refs = relationship("EvidenceRef", back_populates="result")
    review_decisions = relationship("ReviewDecision", back_populates="result")


class EvidenceRef(Base):
    __tablename__ = "evidence_refs"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    result_id = Column(String(36), ForeignKey("verification_results.id"), nullable=False)
    field_id = Column(String(36), ForeignKey("extracted_fields.id"), nullable=True)
    page_id = Column(String(36), ForeignKey("pages.id"), nullable=True)
    bbox = Column(JSONB, nullable=True)
    snippet = Column(Text, nullable=True)

    result = relationship("VerificationResult", back_populates="evidence_refs")


class IntegrityFinding(Base):
    __tablename__ = "integrity_findings"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    check_type = Column(String(100), nullable=False)
    indicator = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False)
    detail = Column(JSONB, nullable=True)
    is_proof = Column(Boolean, default=False)  # always false per policy
    created_at = Column(DateTime, default=utc_now)

    document = relationship("Document", back_populates="integrity_findings")


class ConsistencyEdge(Base):
    __tablename__ = "consistency_edges"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    version_id = Column(String(36), ForeignKey("application_versions.id"), nullable=False)
    field_a_id = Column(String(36), ForeignKey("extracted_fields.id"), nullable=False)
    field_b_id = Column(String(36), ForeignKey("extracted_fields.id"), nullable=False)
    relation = Column(String(100), nullable=False)
    similarity = Column(Float, nullable=True)
    status = Column(String(20), nullable=False)  # CONSISTENT | MISMATCH | FUZZY_MATCH
    detail = Column(JSONB, nullable=True)
    severity = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=utc_now)


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    result_id = Column(String(36), ForeignKey("verification_results.id"), nullable=False)
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    action = Column(String(30), nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    result = relationship("VerificationResult", back_populates="review_decisions")


class Deficiency(Base):
    __tablename__ = "deficiencies"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    version_id = Column(String(36), ForeignKey("application_versions.id"), nullable=False)
    result_id = Column(String(36), ForeignKey("verification_results.id"), nullable=True)
    text = Column(Text, nullable=False)
    due_date = Column(DateTime, nullable=True)
    resolved_in_version_id = Column(String(36), ForeignKey("application_versions.id"), nullable=True)
    created_at = Column(DateTime, default=utc_now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer().with_variant(BigInteger, "postgresql"), primary_key=True, autoincrement=True)
    actor_id = Column(String(36), nullable=True)
    action = Column(String(200), nullable=False)
    object_type = Column(String(100), nullable=True)
    object_id = Column(String(36), nullable=True)
    payload = Column(JSONB, nullable=True)
    prev_hash = Column(String(64), nullable=True)
    event_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now)
    ip_address = Column(String(50), nullable=True)
