from pathlib import Path

WORKFLOW_PATH = Path('.github/workflows/ci.yml')
REQUIREMENTS_PATH = Path('requirements-dev.txt')


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
        'pip install -r requirements-dev.txt',
    ]

    missing = [snippet for snippet in expected_snippets if snippet not in content]
    assert not missing, f"Workflow missing required content: {missing}"

    assert 'pip install -e .' not in content, "Editable install should not be required in CI"


def test_dev_requirements_list_ci_dependencies():
    assert REQUIREMENTS_PATH.exists(), "Expected dev requirements file for CI dependencies"

    content = REQUIREMENTS_PATH.read_text().strip().splitlines()
    expected_packages = {'ruff', 'pytest', 'pytest-cov'}
    missing = sorted(pkg for pkg in expected_packages if not any(pkg in line for line in content))
    assert not missing, f"Dev requirements missing packages: {missing}"
