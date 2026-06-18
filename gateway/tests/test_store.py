"""Tests for the durable SQLite store-and-forward buffer."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
from gateway.store import BufferedMessage, SqliteBuffer

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def buffer(tmp_path: Path) -> SqliteBuffer:
    buf = SqliteBuffer(str(tmp_path / "buffer.sqlite"))
    yield buf
    buf.close()


def test_enqueue_pending_mark_sent_roundtrip(buffer: SqliteBuffer) -> None:
    """The core contract: enqueue -> pending -> mark_sent removes from pending."""
    topic = "farm/org-1/GH1-NODE-01/telemetry"
    id1 = buffer.enqueue(topic, b'{"air_temp_c": 28.5}', ts=1000.0)
    id2 = buffer.enqueue(topic, '{"air_temp_c": 29.1}', ts=1001.0)
    id3 = buffer.enqueue(topic, b'{"air_temp_c": 30.0}', ts=1002.0)

    assert id1 < id2 < id3
    assert buffer.pending_count() == 3

    pending = buffer.pending(limit=10)
    assert [m.id for m in pending] == [id1, id2, id3]  # oldest first (FIFO)
    assert isinstance(pending[0], BufferedMessage)
    # str payloads are stored and returned as bytes losslessly
    assert pending[0].payload == b'{"air_temp_c": 28.5}'
    assert pending[1].payload == b'{"air_temp_c": 29.1}'
    assert pending[0].topic == topic
    assert pending[0].ts == 1000.0

    # Acknowledge the first two; only the third remains pending.
    updated = buffer.mark_sent([id1, id2])
    assert updated == 2
    assert buffer.pending_count() == 1
    remaining = buffer.pending(limit=10)
    assert [m.id for m in remaining] == [id3]


def test_pending_respects_limit(buffer: SqliteBuffer) -> None:
    for i in range(5):
        buffer.enqueue("farm/x/n/telemetry", f"msg-{i}".encode())
    batch = buffer.pending(limit=2)
    assert len(batch) == 2
    assert [m.payload for m in batch] == [b"msg-0", b"msg-1"]
    assert buffer.pending(limit=0) == []


def test_mark_sent_is_idempotent_and_ignores_unknown(buffer: SqliteBuffer) -> None:
    mid = buffer.enqueue("farm/x/n/telemetry", b"once")
    assert buffer.mark_sent([mid]) == 1
    # Second call updates nothing (already sent); unknown ids are no-ops.
    assert buffer.mark_sent([mid]) == 0
    assert buffer.mark_sent([99999]) == 0
    assert buffer.mark_sent([]) == 0
    assert buffer.pending_count() == 0


def test_mark_attempted_increments_counter(buffer: SqliteBuffer) -> None:
    mid = buffer.enqueue("farm/x/n/telemetry", b"retry-me")
    buffer.mark_attempted([mid])
    buffer.mark_attempted([mid])
    (msg,) = buffer.pending(limit=1)
    assert msg.attempts == 2


def test_purge_only_removes_old_sent_rows(buffer: SqliteBuffer) -> None:
    sent_id = buffer.enqueue("farm/x/n/telemetry", b"old-sent")
    unsent_id = buffer.enqueue("farm/x/n/telemetry", b"still-pending")
    buffer.mark_sent([sent_id])

    # Backdate the sent_at so it falls outside the retention window.
    with buffer._lock:  # noqa: SLF001 - white-box test of retention behaviour
        old = time.time() - 10 * 86400
        buffer._conn.execute("UPDATE queue SET sent_at = ? WHERE id = ?", (old, sent_id))
        buffer._conn.commit()

    deleted = buffer.purge(older_than_days=7.0)
    assert deleted == 1
    # The unsent row must never be purged regardless of age.
    assert buffer.pending_count() == 1
    assert buffer.pending(limit=1)[0].id == unsent_id


def test_purge_zero_days_drops_all_sent(buffer: SqliteBuffer) -> None:
    a = buffer.enqueue("t", b"a")
    b = buffer.enqueue("t", b"b")
    buffer.mark_sent([a, b])
    assert buffer.purge(older_than_days=0) == 2
    assert buffer.pending_count() == 0


def test_durability_across_reopen(tmp_path: Path) -> None:
    """Buffered, unsent messages survive a process/instance restart."""
    db = str(tmp_path / "durable.sqlite")
    buf1 = SqliteBuffer(db)
    mid = buf1.enqueue("farm/x/n/telemetry", b"survive-restart", ts=1234.0)
    buf1.close()

    buf2 = SqliteBuffer(db)
    try:
        pending = buf2.pending(limit=10)
        assert [m.id for m in pending] == [mid]
        assert pending[0].payload == b"survive-restart"
        assert pending[0].ts == 1234.0
    finally:
        buf2.close()
