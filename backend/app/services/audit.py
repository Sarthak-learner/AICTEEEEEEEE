"""Hash-chained append-only audit log service.

Each event hash = SHA-256(prev_hash + canonical_payload).
The application role has no UPDATE or DELETE on audit_events.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models import AuditEvent


def _canonical(payload: dict) -> str:
    """Stable JSON serialisation for hashing."""
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def record_event(
    db: Session,
    action: str,
    actor_id: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    payload: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> AuditEvent:
    """Append a hash-chained audit event."""
    # Get the last event's hash
    last = db.query(AuditEvent).order_by(AuditEvent.id.desc()).first()
    prev_hash = last.event_hash if last else "0" * 64

    # Use a consistent timestamp for both hashing and the database model
    now_dt = datetime.now(timezone.utc).replace(tzinfo=None)
    now_str = now_dt.isoformat()

    event_payload = {
        "action": action,
        "actor_id": actor_id,
        "object_type": object_type,
        "object_id": object_id,
        "payload": payload or {},
        "created_at": now_str,
    }
    event_hash = hashlib.sha256(
        (prev_hash + _canonical(event_payload)).encode()
    ).hexdigest()

    ev = AuditEvent(
        actor_id=actor_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        payload=payload or {},
        created_at=now_dt,
        prev_hash=prev_hash,
        event_hash=event_hash,
        ip_address=ip_address,
    )
    db.add(ev)
    db.flush()
    return ev


def verify_chain(db: Session) -> dict:
    """Re-compute all hashes and return first broken link or 'intact'."""
    events = db.query(AuditEvent).order_by(AuditEvent.id.asc()).all()
    prev_hash = "0" * 64
    for ev in events:
        if ev.prev_hash != prev_hash:
            return {"intact": False, "broken_at": ev.id, "reason": "prev_hash mismatch"}
        event_payload = {
            "action": ev.action,
            "actor_id": ev.actor_id,
            "object_type": ev.object_type,
            "object_id": ev.object_id,
            "payload": ev.payload or {},
            "created_at": ev.created_at.isoformat() if ev.created_at else "",
        }
        expected_hash = hashlib.sha256(
            (prev_hash + _canonical(event_payload)).encode()
        ).hexdigest()
        if ev.event_hash != expected_hash:
            return {"intact": False, "broken_at": ev.id, "reason": "hash mismatch"}
        prev_hash = ev.event_hash
    return {"intact": True, "total_events": len(events)}
