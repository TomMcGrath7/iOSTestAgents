"""The version is one number, and it matches the tag it ships under.

The number lived in two files and they drifted apart: `pyproject.toml` said
0.2.0 (correct, and what the v0.2.0 tag packaged) while
`src/iostestagents/__init__.py` said 0.1.0. So `iostestagents.__version__`
reported 0.1.0 for an install whose metadata said 0.2.0. Anything reading the
attribute (a bug report, a `--version` flag, a compatibility check) got the
wrong answer, and nothing in the suite noticed.

Same fix llm-seam and content-ingest took: `__version__` is the single source,
`[tool.hatch.version]` reads it, and the guards below cover the halves an
ordinary unit test cannot see.
"""

from __future__ import annotations

import importlib.metadata
import subprocess
import tomllib
from pathlib import Path

import pytest

import iostestagents

ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    """Parsed rather than scanned: this package's floor is 3.11, so `tomllib` is
    in the stdlib and there is no reason to regex a TOML file."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_the_installed_metadata_matches_the_source():
    """Proves hatch's dynamic version wiring works. If `[tool.hatch.version]` is
    ever removed or mistyped, the build falls back and these diverge, which is
    the state this repo was already in."""
    assert importlib.metadata.version("iostestagents") == iostestagents.__version__


def test_pyproject_declares_no_version_of_its_own():
    """A second copy is a second thing to forget, and here it was forgotten. It
    is asserted gone rather than merely corrected."""
    project = _pyproject()["project"]
    assert "version" not in project
    assert "version" in project.get("dynamic", [])


def _newest_tag() -> str | None:
    """The highest vN.N.N tag, or None when git can't answer.

    `--sort=-v:refname` orders by version rather than by date: a tag cut later
    for an older branch must not be read as "the newest release".
    """
    try:
        out = subprocess.run(
            ["git", "tag", "--list", "v*", "--sort=-v:refname"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    tags = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    return tags[0] if tags else None


def test_the_version_matches_the_newest_tag():
    """Skips rather than fails when there are no tags: a shallow CI checkout or a
    fresh clone has none, and a guard that fails in those is a guard people
    delete. It has to be honest about what it could not check.

    Note this asserts `__version__` equals the *newest* tag, not that `main` is
    at that tag. Commits land on `main` after a release and before the next one;
    they carry the released version until something bumps it, which is the point
    of bumping in the same commit as the change.
    """
    tag = _newest_tag()
    if tag is None:
        pytest.skip("no git tags visible (shallow clone or no git), nothing to compare")
    assert tag.lstrip("v") == iostestagents.__version__, (
        f"the newest tag is {tag} but __version__ is {iostestagents.__version__}. "
        f"Either bump __version__ and re-tag, or the tag was cut before the bump."
    )


def test_the_changelog_documents_this_version():
    """A version with no entry is a version nobody can tell apart from the last
    one."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {iostestagents.__version__}" in changelog
