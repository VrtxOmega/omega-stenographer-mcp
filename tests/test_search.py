"""Tests for FTS5 search and TF-IDF similarity search."""

import pytest
import json
import os
import sys
import tempfile

os.environ["OMEGA_STENOGRAPHER_DIR"] = tempfile.mkdtemp()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from omega_stenographer_mcp_standalone import get_db


@pytest.fixture
def db():
    conn = get_db()
    conn.execute("DELETE FROM exchanges")
    conn.execute("DELETE FROM exchanges_fts")
    conn.commit()

    # Insert test data
    exchanges = [
        ("user", "Fix the authentication bug in the login module", json.dumps(["debug auth"]), json.dumps(["login broken"]), "search-test"),
        ("assistant", "Found JWT secret key mismatch in validation endpoint", json.dumps(["JWT fix applied"]), "[]", "search-test"),
        ("user", "Deploy the fix to production", "[]", "[]", "search-test"),
        ("assistant", "Deployment successful. Monitoring for 24 hours.", json.dumps(["deployed"]), "[]", "search-test"),
    ]

    for role, content, decisions, blockers, sid in exchanges:
        cur = db.execute(
            "INSERT INTO exchanges (role, content, decisions, blockers, session_id) VALUES (?,?,?,?,?)",
            (role, content, decisions, blockers, sid)
        )
        ex_id = cur.lastrowid
        db.execute(
            "INSERT INTO exchanges_fts(rowid, content, decisions, blockers) VALUES (?,?,?,?)",
            (ex_id, content[:4000], decisions, blockers)
        )
    db.commit()
    yield conn
    conn.close()


class TestFTSSearch:
    def test_single_keyword(self, db):
        results = db.execute(
            "SELECT content FROM exchanges_fts WHERE exchanges_fts MATCH 'authentication'"
        ).fetchall()
        assert len(results) == 1
        assert "authentication" in results[0][0].lower()

    def test_or_query(self, db):
        results = db.execute(
            "SELECT content FROM exchanges_fts WHERE exchanges_fts MATCH 'JWT OR authentication'"
        ).fetchall()
        assert len(results) >= 1

    def test_phrase_query(self, db):
        results = db.execute(
            "SELECT content FROM exchanges_fts WHERE exchanges_fts MATCH '\"login module\"'"
        ).fetchall()
        assert len(results) == 1

    def test_no_results(self, db):
        results = db.execute(
            "SELECT content FROM exchanges_fts WHERE exchanges_fts MATCH 'zzzznonexistent'"
        ).fetchall()
        assert len(results) == 0

    def test_search_decisions(self, db):
        results = db.execute(
            "SELECT decisions FROM exchanges_fts WHERE exchanges_fts MATCH 'deployed'"
        ).fetchall()
        assert len(results) >= 1
