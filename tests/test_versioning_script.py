from __future__ import annotations

from pathlib import Path

import pytest


def test_read_version_extracts_project_version(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
        [project]
        version = "1.2.3"
        """
    )

    from scripts import versioning

    assert versioning.read_version(pyproject) == "1.2.3"


def test_ensure_version_is_new_raises_when_tag_exists() -> None:
    from scripts import versioning

    with pytest.raises(ValueError) as exc:
        versioning.ensure_version_is_new("1.2.3", {"v1.2.3", "v1.2.2"})

    assert "already tagged" in str(exc.value)


def test_get_existing_tags_invokes_git(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import versioning

    captured = {}

    def fake_check_output(cmd: list[str], text: bool) -> str:  # type: ignore[override]
        captured["cmd"] = cmd
        captured["text"] = text
        return "v0.1.0\nv0.1.1\n"

    monkeypatch.setattr(versioning.subprocess, "check_output", fake_check_output)

    assert versioning.get_existing_tags() == {"v0.1.0", "v0.1.1"}
    assert captured["cmd"] == ["git", "tag", "--list"]


def test_main_prints_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import versioning

    monkeypatch.setattr(versioning, "read_version", lambda path: "9.9.9")

    versioning.main(["version", "--pyproject", "dummy"])

    captured = capsys.readouterr()
    assert captured.out.strip() == "9.9.9"


def test_main_writes_github_outputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from scripts import versioning

    output_file = tmp_path / "out.txt"
    monkeypatch.setattr(versioning, "read_version", lambda path: "2.0.0")
    monkeypatch.setattr(versioning, "get_existing_tags", lambda: set())

    versioning.main(
        [
            "ensure-new",
            "--pyproject",
            "dummy",
            "--github-output",
            str(output_file),
        ]
    )

    assert output_file.read_text() == "version=2.0.0\ntag=v2.0.0\n"
