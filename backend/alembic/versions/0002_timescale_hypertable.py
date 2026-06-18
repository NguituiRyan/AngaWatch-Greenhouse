"""convert readings to a TimescaleDB hypertable (+ compression/retention policies)

Revision ID: 0002_timescale_hypertable
Revises: 0001_initial
Create Date: 2026-01-01 00:00:01
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_timescale_hypertable"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # hypertables are a no-op on sqlite (used only in unit tests)

    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    op.execute(
        "SELECT create_hypertable('readings', 'time', "
        "chunk_time_interval => INTERVAL '7 days', "
        "if_not_exists => TRUE, migrate_data => TRUE);"
    )
    # Compress chunks older than 14 days, drop raw data older than 1 year.
    op.execute(
        "ALTER TABLE readings SET ("
        "timescaledb.compress, "
        "timescaledb.compress_segmentby = 'device_id');"
    )
    op.execute(
        "SELECT add_compression_policy('readings', INTERVAL '14 days', if_not_exists => TRUE);"
    )
    op.execute(
        "SELECT add_retention_policy('readings', INTERVAL '365 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("SELECT remove_retention_policy('readings', if_exists => TRUE);")
    op.execute("SELECT remove_compression_policy('readings', if_exists => TRUE);")
    # Reverting a hypertable back to a plain table is non-trivial; left as a no-op.
