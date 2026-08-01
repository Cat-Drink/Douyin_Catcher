"""Tests for the reproducible dependency license inventory."""

import json
from pathlib import Path

from scripts.generate_license_report import build_report


PROJECT_ROOT = Path(__file__).parent.parent


def test_report_contains_all_dependency_ecosystems() -> None:
    report = build_report(PROJECT_ROOT, generated_at="2026-08-01")
    assert "Python dependencies" in report
    assert "npm dependencies" in report
    assert "Rust crates" in report
    assert "requirements.txt" in report
    assert "frontend/package-lock.json" in report
    assert "frontend/src-tauri/Cargo.lock" in report
    assert "需人工核实" in report


def test_report_marks_missing_license_metadata(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("example-package>=1.0\n", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {},
                    "node_modules/no-license": {"version": "1.0.0"},
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "frontend" / "src-tauri").mkdir(parents=True)
    (tmp_path / "frontend" / "src-tauri" / "Cargo.lock").write_text(
        'version = 4\n\n[[package]]\nname = "no-license-crate"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )

    report = build_report(tmp_path, generated_at="2026-08-01")
    assert "example-package" in report
    assert "no-license" in report
    assert "no-license-crate" in report
    assert report.count("需人工核实") >= 3
