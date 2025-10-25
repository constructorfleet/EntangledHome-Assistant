"""Smoke tests for CI workflow expectations."""

from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
WORKFLOW_CONTENT = WORKFLOW.read_text()


def test_ci_workflow_includes_lint_and_coverage_upload() -> None:
    """CI pipeline should include linting and coverage upload steps."""

    assert "lint" in WORKFLOW_CONTENT, "Expected dedicated lint job in CI workflow"
    assert "codecov/codecov-action" in WORKFLOW_CONTENT, "Expected coverage upload step"


def test_ci_workflow_runs_targeted_pytest_suites() -> None:
    """CI should run adapter_service and Home Assistant pytest suites explicitly."""

    assert "pytest tests" in WORKFLOW_CONTENT, "Home Assistant tests should run"
    assert "pytest adapter_service/tests" in WORKFLOW_CONTENT, "Adapter service tests should run"
