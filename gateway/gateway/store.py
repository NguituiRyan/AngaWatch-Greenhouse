"""Durable on-disk message buffer backed by SQLite.

:class:`SqliteBuffer` is the persistence layer of the gateway's store-and-forward
design. Every message received from the local broker is ``enqueue``-d here BEFORE
any forward attempt, so an unexpected power loss or process crash can never drop a
reading. Forwarding then reads a batch via ``pending``, publishes it upstream, and
calls ``mark_sent`` only after the broker has acknowledged it. ``purge`` reclaims
disk by deleting old, already-sent rows.

The schema is intentionally minimal and append-only on the hot path:

    queue(id INTEGER PK, topic TEXT, payload BLOB, ts REAL,
          enqueued_at REAL, sent INTEGER, sent_at REAL, attempts INTEGER)

SQLite is run in WAL mode for crash-safe concurrent reads/writes from a single
process. The class is safe to share across the gateway's threads: every public
method serialises access with an internal lock and uses short-lived transactions.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger("gateway.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic       TEXT    NOT NULL,
    payload     BLOB    NOT NULL,
    ts          REAL    NOT NULL,
    enqueued_at REAL    NOT NULL,
    sent        INTEGER NOT NULL DEFAULT 0,
    sent_at     REAL,
    attempts    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_queue_pending ON queue (sent, id);
CREATE INDEX IF NOT EXISTS ix_queue_purge ON queue (sent, sent_at);
"""


@dataclass(frozen=True, slots=True)
class BufferedMessage:
    """One buffered MQTT message awaiting (or past) forwarding.

    ``payload`` is returned as raw ``bytes`` so the forwarder can republish the
    exact wire bytes it received without any lossy re-encoding.
    """

    id: int
    topic: str
    payload: bytes
    ts: float
    attempts: int


class SqliteBuffer:
    """A durable FIFO-ish buffer of MQTT messages backed by a SQLite file.

    Parameters
    ----------
    db_path:
        Filesystem path to the SQLite database. ``":memory:"`` is accepted for
        tests (note: an in-memory DB lives only as long as this instance).
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        # check_same_thread=False because the buffer is shared across the MQTT
        # network thread and the forwarder thread; our own lock serialises use.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._configure()
        self._init_schema()
        logger.info("sqlite buffer ready at %s", db_path)

    # -- lifecycle ---------------------------------------------------------

    def _configure(self) -> None:
        cur = self._conn.cursor()
        # WAL gives crash-safe durability with good write throughput; NORMAL
        # sync is the right durability/latency trade-off for an edge buffer.
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        """Close the underlying connection. Idempotent."""
        with self._lock, contextlib.suppress(sqlite3.Error):
            self._conn.close()

    def __enter__(self) -> SqliteBuffer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- write path --------------------------------------------------------

    def enqueue(self, topic: str, payload: bytes | str, ts: float | None = None) -> int:
        """Durably append one message and return its assigned row id.

        ``ts`` is the message's logical timestamp (epoch seconds). When omitted
        it defaults to wall-clock now. ``enqueued_at`` always records arrival
        time so ordering survives clock adjustments on the device.
        """
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        now = time.time()
        msg_ts = now if ts is None else float(ts)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO queue (topic, payload, ts, enqueued_at, sent, attempts) "
                "VALUES (?, ?, ?, ?, 0, 0)",
                (topic, payload, msg_ts, now),
            )
            self._conn.commit()
            row_id = int(cur.lastrowid or 0)
        logger.debug("enqueued id=%s topic=%s bytes=%d", row_id, topic, len(payload))
        return row_id

    # -- read path ---------------------------------------------------------

    def pending(self, limit: int = 100) -> list[BufferedMessage]:
        """Return up to ``limit`` unsent messages in insertion order (oldest first)."""
        if limit <= 0:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, topic, payload, ts, attempts FROM queue "
                "WHERE sent = 0 ORDER BY id ASC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [
            BufferedMessage(
                id=int(r["id"]),
                topic=str(r["topic"]),
                payload=bytes(r["payload"]),
                ts=float(r["ts"]),
                attempts=int(r["attempts"]),
            )
            for r in rows
        ]

    def pending_count(self) -> int:
        """Return the number of messages still awaiting forwarding."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM queue WHERE sent = 0").fetchone()
        return int(row["n"]) if row else 0

    # -- acknowledge / cleanup --------------------------------------------

    def mark_sent(self, ids: Sequence[int]) -> int:
        """Mark the given row ids as forwarded. Returns the number updated."""
        ids = [int(i) for i in ids]
        if not ids:
            return 0
        now = time.time()
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE queue SET sent = 1, sent_at = ? "  # noqa: S608 - ids are ints
                f"WHERE id IN ({placeholders}) AND sent = 0",
                (now, *ids),
            )
            self._conn.commit()
            updated = cur.rowcount
        logger.debug("marked sent ids=%s updated=%d", ids, updated)
        return int(updated)

    def mark_attempted(self, ids: Sequence[int]) -> int:
        """Increment the retry counter for the given ids (a forward failed)."""
        ids = [int(i) for i in ids]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE queue SET attempts = attempts + 1 "  # noqa: S608 - ids are ints
                f"WHERE id IN ({placeholders})",
                tuple(ids),
            )
            self._conn.commit()
            updated = cur.rowcount
        return int(updated)

    def purge(self, older_than_days: float = 7.0) -> int:
        """Delete already-sent rows older than ``older_than_days``. Returns count.

        Pass ``older_than_days <= 0`` to purge every sent row immediately. Unsent
        rows are never deleted, no matter their age — durability comes first.
        """
        with self._lock:
            if older_than_days <= 0:
                cur = self._conn.execute("DELETE FROM queue WHERE sent = 1")
            else:
                cutoff = time.time() - older_than_days * 86400.0
                cur = self._conn.execute(
                    "DELETE FROM queue WHERE sent = 1 AND sent_at IS NOT NULL AND sent_at < ?",
                    (cutoff,),
                )
            self._conn.commit()
            deleted = cur.rowcount
        if deleted:
            logger.info("purged %d sent rows older than %.1f days", deleted, older_than_days)
        return int(deleted)
