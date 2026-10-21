"""Checks that the Milestone 1 project layout is present and importable."""

from pathlib import Path

import ai_governance
from ai_governance import (
    api,
    assessment,
    db,
    extraction,
    ingestion,
    reporting,
    workflow,
)

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_FILES = (
    "pyproject.toml",
    "README.md",
    ".gitignore",
    ".env.example",
    "src/ai_governance/__init__.py",
    "src/ai_governance/config.py",
    "src/ai_governance/api/__init__.py",
    "src/ai_governance/assessment/__init__.py",
    "src/ai_governance/db/__init__.py",
    "src/ai_governance/extraction/__init__.py",
    "src/ai_governance/ingestion/__init__.py",
    "src/ai_governance/reporting/__init__.py",
    "src/ai_governance/workflow/__init__.py",
    "frontend/.gitkeep",
    "data/.gitkeep",
)


def test_package_exposes_version() -> None:
    assert ai_governance.__version__ == "0.1.0"


def test_boundary_packages_import() -> None:
    modules = (api, assessment, db, extraction, ingestion, reporting, workflow)
    assert all(module.__doc__ for module in modules)


def test_foundation_files_exist() -> None:
    missing = [relative for relative in EXPECTED_FILES if not (ROOT / relative).is_file()]
    assert missing == []


def test_env_example_documents_variables_without_secrets() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "DATABASE_URL=" in text
    assert "LLM_ENABLED=false" in text
    assert "sk-" not in text


def test_gitignore_excludes_secrets_and_the_virtualenv() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in text
    assert ".venv/" in text
    assert "!.env.example" in text
