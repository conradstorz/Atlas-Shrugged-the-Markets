from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class JournalEntry:
    id: int
    symbol: str
    entry_date: str
    decision: str
    thesis: str
    confidence: int | None
    max_allocation_percent: float | None
    change_mind_conditions: str | None
    notes: str | None


def add_journal_entry(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    decision: str,
    thesis: str,
    confidence: int | None = None,
    max_allocation_percent: float | None = None,
    change_mind_conditions: str | None = None,
    notes: str | None = None,
) -> int:
    """Add an explainable decision-journal entry."""
    if confidence is not None and not 0 <= confidence <= 100:
        raise ValueError("confidence must be between 0 and 100")
    cursor = conn.execute(
        """
        INSERT INTO decision_journal_entry (
            symbol, decision, thesis, confidence, max_allocation_percent,
            change_mind_conditions, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol.upper(),
            decision,
            thesis,
            confidence,
            max_allocation_percent,
            change_mind_conditions,
            notes,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_journal_entries(conn: sqlite3.Connection, symbol: str | None = None, limit: int = 20) -> list[JournalEntry]:
    """List recent journal entries, optionally filtered by symbol."""
    if symbol:
        rows = conn.execute(
            """
            SELECT * FROM decision_journal_entry
            WHERE symbol = ?
            ORDER BY entry_date DESC, id DESC
            LIMIT ?
            """,
            (symbol.upper(), limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM decision_journal_entry
            ORDER BY entry_date DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [JournalEntry(**dict(row)) for row in rows]
