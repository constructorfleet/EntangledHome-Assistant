from __future__ import annotations

import argparse
import subprocess
import tomllib
from pathlib import Path
from typing import Any, Iterable


def _load_pyproject(pyproject_path: Path) -> dict[str, Any]:
    with pyproject_path.open("rb") as handle:
        return tomllib.load(handle)


def read_version(pyproject_path: Path) -> str:
    data = _load_pyproject(pyproject_path)
    return data["project"]["version"]


def ensure_version_is_new(version: str, existing_tags: Iterable[str]) -> None:
    tag = build_tag(version)
    if tag in _as_tag_set(existing_tags):
        raise ValueError(f"Version {version} is already tagged")


def build_tag(version: str) -> str:
    return f"v{version}"


def get_existing_tags() -> set[str]:
    output = subprocess.check_output(["git", "tag", "--list"], text=True)
    return _as_tag_set(output.splitlines())


def _as_tag_set(existing_tags: Iterable[str]) -> set[str]:
    return {tag.strip() for tag in existing_tags if tag.strip()}


def main(argv: Iterable[str] | None = None) -> None:
    parser = _build_parser()
    args = _parse_args(parser, argv)

    pyproject_path = Path(args.pyproject)
    version = read_version(pyproject_path)
    tag = build_tag(version)

    if args.command == "version":
        print(version)
    elif args.command == "tag":
        print(tag)
    elif args.command == "ensure-new":
        ensure_version_is_new(version, get_existing_tags())
        print(tag)
    else:  # pragma: no cover
        parser.error(f"Unsupported command: {args.command}")

    if args.github_output:
        _write_github_output(Path(args.github_output), version, tag)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Versioning helper utilities")
    parser.add_argument("command", choices=("version", "tag", "ensure-new"))
    parser.add_argument("--pyproject", default="pyproject.toml")
    parser.add_argument("--github-output")
    return parser


def _write_github_output(path: Path, version: str, tag: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"version={version}\n")
        handle.write(f"tag={tag}\n")


def _parse_args(parser: argparse.ArgumentParser, argv: Iterable[str] | None) -> argparse.Namespace:
    return parser.parse_args(list(argv) if argv is not None else None)


if __name__ == "__main__":  # pragma: no cover - convenience entrypoint
    main()
