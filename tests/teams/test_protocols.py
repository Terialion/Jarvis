"""Tests for team protocols — shutdown and plan approval FSMs (s10)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.jarvis.core.teams.protocols import PlanTracker, ShutdownTracker


class TestShutdownTracker:
    def test_create_pending(self):
        st = ShutdownTracker()
        req_id = st.create("alice")
        status = st.status(req_id)
        assert status["target"] == "alice"
        assert status["status"] == "pending"

    def test_resolve_approved(self):
        st = ShutdownTracker()
        req_id = st.create("alice")
        result = st.resolve(req_id, approved=True)
        assert result["status"] == "approved"
        assert st.status(req_id)["status"] == "approved"

    def test_resolve_rejected(self):
        st = ShutdownTracker()
        req_id = st.create("bob")
        result = st.resolve(req_id, approved=False)
        assert result["status"] == "rejected"

    def test_unknown_request_id(self):
        st = ShutdownTracker()
        assert st.status("nope") is None
        assert st.resolve("nope", True) is None


class TestPlanTracker:
    def test_submit_pending(self):
        pt = PlanTracker()
        req_id = pt.submit("alice", "Refactor auth module")
        status = pt.status(req_id)
        assert status["from"] == "alice"
        assert status["plan"] == "Refactor auth module"
        assert status["status"] == "pending"

    def test_review_approved(self):
        pt = PlanTracker()
        req_id = pt.submit("bob", "Add tests")
        result = pt.review(req_id, approved=True, feedback="Looks good")
        assert result["status"] == "approved"
        assert result["feedback"] == "Looks good"

    def test_review_rejected(self):
        pt = PlanTracker()
        req_id = pt.submit("bob", "Deploy to prod directly")
        result = pt.review(req_id, approved=False, feedback="Need staging first")
        assert result["status"] == "rejected"
        assert result["feedback"] == "Need staging first"

    def test_unknown_request_id(self):
        pt = PlanTracker()
        assert pt.status("nope") is None
        assert pt.review("nope", True) is None
