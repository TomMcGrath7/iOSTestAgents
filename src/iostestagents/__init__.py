"""iostestagents — AI-powered iOS app testing framework."""

# The one place the version lives; `pyproject.toml` reads it from here via
# `[tool.hatch.version]`. It said 0.1.0 while `pyproject.toml` said 0.2.0, so
# `iostestagents.__version__` disagreed with the installed metadata under the
# v0.2.0 tag. Bump it in the same commit as the change, then tag; see the
# release checklist in CLAUDE.md.
__version__ = "0.2.0"
