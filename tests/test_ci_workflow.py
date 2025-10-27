"""Smoke tests for CI workflow expectations."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
WORKFLOW_CONTENT = WORKFLOW.read_text()


@lru_cache(maxsize=1)
def load_workflow() -> dict:
    """Load the CI workflow YAML for targeted assertions."""

    return yaml.safe_load(WORKFLOW_CONTENT)


def extract_run_step(job_id: str, step_name: str) -> str:
    """Return the run command for the named step in the specified job."""

    workflow = load_workflow()
    steps = workflow["jobs"][job_id]["steps"]
    for step in steps:
        if step.get("name") == step_name:
            return step["run"]
    raise KeyError(f"{step_name} not found in {job_id} steps: {steps}")


def test_ci_workflow_includes_lint_and_coverage_upload() -> None:
    """CI pipeline should include linting and coverage upload steps."""

    assert "lint" in WORKFLOW_CONTENT, "Expected dedicated lint job in CI workflow"
    assert "codecov/codecov-action" in WORKFLOW_CONTENT, "Expected coverage upload step"


def test_ci_workflow_runs_targeted_pytest_suites() -> None:
    """CI should run adapter_service and Home Assistant pytest suites explicitly."""

    assert "pytest tests" in WORKFLOW_CONTENT, "Home Assistant tests should run"
    assert "pytest adapter_service/tests" in WORKFLOW_CONTENT, "Adapter service tests should run"


def test_home_assistant_suite_generates_dedicated_coverage_xml() -> None:
    """Home Assistant workflow job must emit coverage XML for Codecov upload."""

    run_command = extract_run_step("home-assistant-tests", "Run pytest (Home Assistant)")
    assert "--cov=custom_components.entangledhome" in run_command
    assert "--cov-report=xml:coverage-home-assistant.xml" in run_command


def test_adapter_suite_generates_dedicated_coverage_xml() -> None:
    """Adapter workflow job must emit coverage XML for Codecov upload."""

    run_command = extract_run_step("adapter-service-tests", "Run pytest (Adapter)")
    assert "--cov=adapter_service" in run_command
    assert "--cov-report=xml:coverage-adapter-service.xml" in run_command
