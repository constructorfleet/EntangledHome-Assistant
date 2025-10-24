from pathlib import Path

import tomllib

WORKFLOW_PATH = Path('.github/workflows/ci.yml')
PYPROJECT_PATH = Path('pyproject.toml')


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
        'pyproject.toml',
        'pip install .[dev]',
    ]

    missing = [snippet for snippet in expected_snippets if snippet not in content]
    assert not missing, f"Workflow missing required content: {missing}"

    assert 'pip install -e .' not in content, "Editable install should not be required in CI"


def test_pyproject_lists_ci_dependencies():
    assert PYPROJECT_PATH.exists(), "Expected pyproject.toml to define project metadata"

    content = tomllib.loads(PYPROJECT_PATH.read_text())
    optional_dependencies = content.get('project', {}).get('optional-dependencies', {})
    dev_dependencies = optional_dependencies.get('dev', [])

    expected_packages = {'ruff', 'pytest', 'pytest-cov'}
    missing = sorted(pkg for pkg in expected_packages if not any(pkg in dep for dep in dev_dependencies))
    assert not missing, f"Dev extra missing packages: {missing}"
