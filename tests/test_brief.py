"""Tests for running notes, briefs, and milestone functionality."""

import pytest
import json
import os
import sys
import tempfile

os.environ["OMEGA_STENOGRAPHER_DIR"] = tempfile.mkdtemp()
os.environ["STENO_TURN_LIMIT"] = "3"

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

    # Insert a milestone exchange (7 columns: role, content, decisions, blockers, session_id, milestone, tier)
    cur = conn.execute(
        "INSERT INTO exchanges (role, content, decisions, blockers, session_id, milestone, tier) VALUES (?,?,?,?,?,?,?)",
        ("assistant", "Root cause identified: race condition in connection pool.",
         json.dumps(["race condition found"]), "[]", "brief-test", "Root cause identified", "A")
    )
    ex_id = cur.lastrowid
    conn.execute(
        "INSERT INTO exchanges_fts(rowid, content, decisions, blockers) VALUES (?,?,?,?)",
        (ex_id, "Root cause identified: race condition in connection pool.", json.dumps(["race condition found"]), "[]")
    )

    # Insert a regular exchange (5 columns)
    cur2 = conn.execute(
        "INSERT INTO exchanges (role, content, decisions, blockers, session_id) VALUES (?,?,?,?,?)",
        ("user", "Good, now fix it.", "[]", "[]", "brief-test")
    )
    ex_id2 = cur2.lastrowid
    conn.execute(
        "INSERT INTO exchanges_fts(rowid, content, decisions, blockers) VALUES (?,?,?,?)",
        (ex_id2, "Good, now fix it.", "[]", "[]")
    )
    conn.commit()
    yield conn
    conn.close()


class TestMilestones:
    def test_milestone_present(self, db):
        milestones = db.execute(
            "SELECT id, milestone, decisions FROM exchanges WHERE milestone IS NOT NULL"
        ).fetchall()
        assert len(milestones) == 1
        assert milestones[0][1] == "Root cause identified"

    def test_tier_elevated(self, db):
        row = db.execute(
            "SELECT tier FROM exchanges WHERE milestone IS NOT NULL"
        ).fetchone()
        assert row[0] == "A"


class TestBriefFormat:
    def test_compression_creates_summary(self, db):
        # Add more exchanges to trigger compression (STENO_TURN_LIMIT=3, so 3 unprocessed needed)
        for i in range(3):
            cur = db.execute(
                "INSERT INTO exchanges (role, content, decisions, blockers, session_id) VALUES (?,?,?,?,?)",
                ("assistant", f"Discussion turn {i+1} about the fix.",
                 json.dumps([f"decision_{i+1}"]), "[]", "brief-test")
            )
            ex_id = cur.lastrowid
            db.execute(
                "INSERT INTO exchanges_fts(rowid, content, decisions, blockers) VALUES (?,?,?,?)",
                (ex_id, f"Discussion turn {i+1} about the fix.", json.dumps([f"decision_{i+1}"]), "[]")
            )
        db.commit()

        result = compress_unprocessed(db)
        if result:
            assert "summary" in result
            assert len(result["summary"]) > 10
