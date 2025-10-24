from pathlib import Path

import tomllib

WORKFLOW_PATH = Path('.github/workflows/ci.yml')
PYPROJECT_PATH = Path('pyproject.toml')
SETUP_SCRIPT_PATH = Path('scripts/setup_env.sh')
README_PATH = Path('README.md')


def test_ci_workflow_exists_and_runs_linters_and_tests():
    assert WORKFLOW_PATH.exists(), "Expected CI workflow configuration at .github/workflows/ci.yml"

    content = WORKFLOW_PATH.read_text()

    expected_snippets = [
        "python-version: '3.13'",
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


def test_pyproject_lists_dev_extra_dependencies():
    assert PYPROJECT_PATH.exists(), "Expected pyproject.toml to define project metadata"

    content = tomllib.loads(PYPROJECT_PATH.read_text())
    optional_dependencies = content.get('project', {}).get('optional-dependencies', {})
    dev_dependencies = optional_dependencies.get('dev', [])

    expected_packages = {
        'ruff',
        'pytest',
        'pytest-homeassistant-custom-component',
        'fastapi',
        'uvicorn',
        'httpx',
    }
    missing = sorted(pkg for pkg in expected_packages if not any(pkg in dep for dep in dev_dependencies))
    assert not missing, f"Dev extra missing packages: {missing}"

    uv_config = content.get('tool', {}).get('uv', {})
    assert uv_config.get('python') == '3.13', "Expected [tool.uv] python version to be 3.13"


def test_setup_env_script_creates_virtualenv_and_installs_dev_extras():
    assert SETUP_SCRIPT_PATH.exists(), "Expected scripts/setup_env.sh to exist for environment setup"

    content = SETUP_SCRIPT_PATH.read_text()

    expected_snippets = [
        '#!/usr/bin/env bash',
        'python3.13 -m venv',
        'source',
        'pip install --upgrade pip',
        "pip install -e '.[dev]'",
    ]

    missing = [snippet for snippet in expected_snippets if snippet not in content]
    assert not missing, f"Setup script missing required content: {missing}"


def test_readme_documents_development_workflow():
    assert README_PATH.exists(), "Expected README.md to document project workflows"

    content = README_PATH.read_text()

    assert '## Development' in content, "README should include a Development section"
    assert 'scripts/setup_env.sh' in content, "Development section should reference setup script"
    assert 'pytest' in content, "Development instructions should mention running tests"
    assert 'ruff' in content, "Development instructions should mention linting with ruff"
