"""
Database access layer: engine/session setup plus the small set of helpers the
pipeline needs (dedupe check, persist an invoice, write to the audit log).

Updated with new fields: buyer_company_name, ack_no, ack_date, buyer_order_no,
eway_bill_no, igst/cgst/sgst, and line item hsn_code/quantity_unit/rate_per_unit.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from . import config
from .models import Base, Invoice, LineItem, ProcessingLog
from .schemas import InvoiceExtraction

engine_kwargs = {
    "future": True,
    "pool_pre_ping": True,
}

if config.DATABASE_URL.startswith("postgresql"):
    engine_kwargs["pool_recycle"] = 300  # recycle connections every 5 minutes for serverless DBs

_engine = create_engine(config.DATABASE_URL, **engine_kwargs)
_SessionFactory = sessionmaker(bind=_engine, future=True, expire_on_commit=False)


def init_db() -> None:
    """Create tables if they don't exist yet."""
    Base.metadata.create_all(_engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session — commits on success, rolls back on error."""
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def already_processed(source_hash: str) -> bool:
    """True if we've already stored a file with this exact content hash."""
    with session_scope() as s:
        found = s.scalar(select(Invoice.id).where(Invoice.source_hash == source_hash))
        return found is not None


def find_duplicate(vendor_name: str, invoice_number: str) -> Optional[int]:
    """Return the id of an existing invoice with the same vendor+number, if any."""
    with session_scope() as s:
        return s.scalar(
            select(Invoice.id).where(
                Invoice.vendor_name == vendor_name,
                Invoice.invoice_number == invoice_number,
            )
        )


def store_invoice(
    data: InvoiceExtraction,
    *,
    source_file: str,
    source_hash: str,
    raw_text: str,
    status: str = "stored",
) -> int:
    """Persist a validated invoice and its line items. Returns the new row id."""
    with session_scope() as s:
        invoice = Invoice(
            invoice_number=data.invoice_number,
            vendor_name=data.vendor_name,
            receiver_details=data.receiver_details,
            state=data.state,
            broker=data.broker,
            bill_amount=data.bill_amount,
            invoice_date=data.invoice_date,
            due_date=data.due_date,
            confidence=data.confidence,
            status=status,
            source_file=source_file,
            source_hash=source_hash,
            raw_text=raw_text,
            line_items=[
                LineItem(
                    description=li.description,
                    design_no=li.design_no,
                    color=li.color,
                    pcs=li.pcs,
                    rate=li.rate,
                    amount=li.amount,
                )
                for li in data.line_items
            ],
        )
        s.add(invoice)
        s.flush()
        return invoice.id


def log_event(
    *, source_file: str, source_hash: str, stage: str, outcome: str, detail: str = ""
) -> None:
    """Append one row to the processing audit trail."""
    with session_scope() as s:
        s.add(
            ProcessingLog(
                source_file=source_file,
                source_hash=source_hash,
                stage=stage,
                outcome=outcome,
                detail=detail[:4000],
            )
        )


# ---------------------------------------------------------------------------
# Read helpers used by the web API. These return plain dicts (not ORM objects)
# so callers never touch a detached/expired SQLAlchemy instance.
# ---------------------------------------------------------------------------
def _invoice_to_dict(inv: Invoice, with_items: bool = False) -> dict:
    data = {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "vendor_name": inv.vendor_name,
        "receiver_details": inv.receiver_details,
        "state": inv.state,
        "broker": inv.broker,
        "bill_amount": inv.bill_amount,
        "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "confidence": inv.confidence,
        "status": inv.status,
        "source_file": Path(inv.source_file).name if inv.source_file else None,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }
    if with_items:
        data["line_items"] = [
            {
                "description": li.description,
                "design_no": li.design_no,
                "color": li.color,
                "pcs": li.pcs,
                "rate": li.rate,
                "amount": li.amount,
            }
            for li in inv.line_items
        ]
    return data


def list_invoices(status: str | None = None, limit: int = 200) -> list[dict]:
    with session_scope() as s:
        stmt = select(Invoice).order_by(Invoice.created_at.desc()).limit(limit)
        if status:
            stmt = select(Invoice).where(Invoice.status == status).order_by(
                Invoice.created_at.desc()
            ).limit(limit)
        return [_invoice_to_dict(inv) for inv in s.scalars(stmt).all()]


def get_invoice(invoice_id: int) -> dict | None:
    with session_scope() as s:
        inv = s.get(Invoice, invoice_id)
        return _invoice_to_dict(inv, with_items=True) if inv else None


def set_invoice_status(invoice_id: int, status: str) -> bool:
    with session_scope() as s:
        inv = s.get(Invoice, invoice_id)
        if not inv:
            return False
        inv.status = status
        return True


def delete_invoice(invoice_id: int) -> bool:
    with session_scope() as s:
        inv = s.get(Invoice, invoice_id)
        if not inv:
            return False
        s.delete(inv)
        return True


def counters() -> dict:
    from sqlalchemy import func

    with session_scope() as s:
        return {
            "stored": s.scalar(select(func.count(Invoice.id))) or 0,
            "needs_review": s.scalar(
                select(func.count(Invoice.id)).where(Invoice.status == "needs_review")
            ) or 0,
            "total_value": float(s.scalar(select(func.sum(Invoice.bill_amount))) or 0.0),
        }


def recent_logs(limit: int = 25) -> list[dict]:
    with session_scope() as s:
        rows = s.scalars(
            select(ProcessingLog).order_by(ProcessingLog.created_at.desc()).limit(limit)
        ).all()
        return [
            {
                "stage": r.stage,
                "outcome": r.outcome,
                "source_file": Path(r.source_file).name if r.source_file else None,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
