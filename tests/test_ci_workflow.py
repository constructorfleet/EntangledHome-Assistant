from pathlib import Path

WORKFLOW_PATH = Path('.github/workflows/ci.yml')


def test_ci_workflow_exists_and_runs_linters_and_tests():
    assert WORKFLOW_PATH.exists(), "Expected CI workflow configuration at .github/workflows/ci.yml"

    content = WORKFLOW_PATH.read_text()

    expected_snippets = [
        "python-version: '3.12'",
        'ruff check',
        'pytest',
        'adapter-service',
        'home-assistant',
        'actions/upload-artifact',
        'coverage',
        'pytest-homeassistant-custom-component',
    ]

    missing = [snippet for snippet in expected_snippets if snippet not in content]
    assert not missing, f"Workflow missing required content: {missing}"
