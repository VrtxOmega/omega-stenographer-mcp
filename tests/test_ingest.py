"""Tests for turn ingestion, decision extraction, and blocker extraction."""

import pytest
import json
import os
import sys
import tempfile

# Use a temp dir for test data
os.environ["OMEGA_STENOGRAPHER_DIR"] = tempfile.mkdtemp()

# Import the module under test
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from omega_stenographer_mcp_standalone import (
    get_db, extract_decisions, extract_blockers,
    tokenize, tfidf_embed, cosine_sim,
)


@pytest.fixture
def db():
    """Fresh database for each test."""
    conn = get_db()
    conn.execute("DELETE FROM exchanges")
    conn.execute("DELETE FROM exchanges_fts")
    conn.commit()
    yield conn
    conn.close()


class TestDecisionExtraction:
    def test_decided_pattern(self):
        text = "I decided to use JWT for authentication. The old session-based approach was too slow."
        decisions = extract_decisions(text)
        assert any("JWT" in d for d in decisions)

    def test_chose_pattern(self):
        text = "After evaluating three libraries, I chose fastembed for ONNX-based embeddings."
        decisions = extract_decisions(text)
        assert any("fastembed" in d for d in decisions)

    def test_key_finding(self):
        text = "Key finding: the database connection pool was exhausting at 50 concurrent users."
        decisions = extract_decisions(text)
        assert any("database connection pool" in d for d in decisions)

    def test_arrow_pattern(self):
        text = "→ Switched from Poetry to setuptools for pyproject.toml compatibility."
        decisions = extract_decisions(text)
        assert any("setuptools" in d for d in decisions)

    def test_no_decisions(self):
        text = "The sky is blue and the weather is pleasant today."
        decisions = extract_decisions(text)
        assert len(decisions) == 0

    def test_short_matches_filtered(self):
        text = "I decided to go."
        decisions = extract_decisions(text)
        # "go" is too short (< 10 chars) — should be filtered
        assert len(decisions) == 0


class TestBlockerExtraction:
    def test_blocked_on(self):
        text = "Blocked on the missing API key for OpenAI. Need to get it from the admin."
        blockers = extract_blockers(text)
        assert any("API key" in b for b in blockers)

    def test_error_pattern(self):
        text = "Error connecting to the database: connection refused on port 5432."
        blockers = extract_blockers(text)
        assert any("5432" in b for b in blockers)

    def test_cannot_pattern(self):
        text = "Cannot proceed without the updated SSL certificate. The old one expired yesterday."
        blockers = extract_blockers(text)
        assert any("SSL certificate" in b for b in blockers)

    def test_no_blockers(self):
        text = "Everything is working perfectly. All tests pass."
        blockers = extract_blockers(text)
        assert len(blockers) == 0


class TestIngestion:
    def test_ingest_creates_exchange(self, db):
        db.execute(
            "INSERT INTO exchanges (role, content, decisions, blockers, session_id) VALUES (?,?,?,?,?)",
            ("user", "Test message", json.dumps(["decision1"]), json.dumps(["blocker1"]), "test-session")
        )
        db.commit()
        row = db.execute("SELECT * FROM exchanges WHERE session_id='test-session'").fetchone()
        assert row is not None
        assert row[1] == "user"
        assert "Test message" in row[2]

    def test_fts_index_on_ingest(self, db):
        cur = db.execute(
            "INSERT INTO exchanges (role, content, decisions, blockers, session_id) VALUES (?,?,?,?,?)",
            ("assistant", "Unique searchable phrase zxcvbnm", "[]", "[]", "fts-test")
        )
        ex_id = cur.lastrowid
        db.execute(
            "INSERT INTO exchanges_fts(rowid, content, decisions, blockers) VALUES (?,?,?,?)",
            (ex_id, "Unique searchable phrase zxcvbnm", "[]", "[]")
        )
        db.commit()
        results = db.execute(
            "SELECT content FROM exchanges_fts WHERE exchanges_fts MATCH 'zxcvbnm'"
        ).fetchall()
        assert len(results) > 0


class TestEmbeddings:
    def test_tokenize(self):
        tokens = tokenize("Hello World! This is a test.")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_tfidf_dimensions(self):
        vec = tfidf_embed("Some test text for embedding")
        assert len(vec) == 128

    def test_tfidf_unit_vector(self):
        vec = tfidf_embed("A meaningful sentence with enough words to test")
        norm = sum(v * v for v in vec) ** 0.5
        assert abs(norm - 1.0) < 0.01

    def test_cosine_identical(self):
        vec = tfidf_embed("identical text")
        sim = cosine_sim(vec, vec)
        assert abs(sim - 1.0) < 0.01

    def test_cosine_different(self):
        a = tfidf_embed("authentication bug JWT token validation")
        b = tfidf_embed("weather forecast sunny day tomorrow")
        sim = cosine_sim(a, b)
        assert sim < 0.5
