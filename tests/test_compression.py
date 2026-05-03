"""Tests for context compression — threshold triggers, tier assignment, source tracking."""

import pytest
import json
import os
import sys
import tempfile

os.environ["OMEGA_STENOGRAPHER_DIR"] = tempfile.mkdtemp()
os.environ["STENO_TURN_LIMIT"] = "4"  # Lower threshold for testing

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from omega_stenographer_mcp_standalone import get_db, compress_unprocessed


@pytest.fixture
def db():
    conn = get_db()
    conn.execute("DELETE FROM exchanges")
    conn.execute("DELETE FROM exchanges_fts")
    conn.execute("DELETE FROM briefs")
    conn.execute("DELETE FROM briefs_fts")
    conn.commit()
    yield conn
    conn.close()


def populate_turns(db, count, with_decisions=True):
    """Insert N exchange rows."""
    for i in range(count):
        content = f"Turn {i+1}: Some technical discussion about debugging."
        decisions = json.dumps(["decision_{}".format(i)]) if with_decisions else "[]"
        blockers = json.dumps(["blocker_{}".format(i)]) if with_decisions else "[]"
        cur = db.execute(
            "INSERT INTO exchanges (role, content, decisions, blockers, session_id) VALUES (?,?,?,?,?)",
            ("assistant", content, decisions, blockers, "compression-test")
        )
        ex_id = cur.lastrowid
        db.execute(
            "INSERT INTO exchanges_fts(rowid, content, decisions, blockers) VALUES (?,?,?,?)",
            (ex_id, content[:4000], decisions, blockers)
        )
    db.commit()


class TestCompressionThreshold:
    def test_no_compression_below_limit(self, db):
        populate_turns(db, 2)  # Below STENO_TURN_LIMIT=4
        result = compress_unprocessed(db)
        assert result is None

    def test_compression_at_threshold(self, db):
        populate_turns(db, 4)  # At STENO_TURN_LIMIT=4
        result = compress_unprocessed(db)
        assert result is not None
        assert result["turn_count"] == 4

    def test_compression_mark_compressed(self, db):
        populate_turns(db, 4)
        compress_unprocessed(db)
        remaining = db.execute(
            "SELECT COUNT(*) FROM exchanges WHERE compressed=0"
        ).fetchone()[0]
        assert remaining == 0


class TestTierAssignment:
    def test_tier_a_with_decisions(self, db):
        populate_turns(db, 4, with_decisions=True)
        result = compress_unprocessed(db)
        assert result["tier"] == "A"

    def test_tier_b_without_decisions(self, db):
        populate_turns(db, 4, with_decisions=False)
        result = compress_unprocessed(db)
        assert result["tier"] == "B"


class TestSourceTracking:
    def test_brief_records_source_turns(self, db):
        populate_turns(db, 4)
        compress_unprocessed(db)
        brief = db.execute("SELECT id, source_turns FROM briefs ORDER BY id DESC LIMIT 1").fetchone()
        assert brief is not None
        source_turns = json.loads(brief[1])
        assert len(source_turns) == 4

    def test_brief_fts_indexed(self, db):
        populate_turns(db, 4, with_decisions=True)
        compress_unprocessed(db)
        results = db.execute(
            "SELECT summary FROM briefs_fts WHERE briefs_fts MATCH 'decision'"
        ).fetchall()
        assert len(results) > 0
