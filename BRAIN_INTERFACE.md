# Brain interface

How Tom's [Personal-AI-Brain](https://github.com/TomMcGrath7/Personal-AI-Brain) works
in this repo. It is read by `brain/code_flow.py::repo_config` when a code task runs
here, and its presence is what puts this repo in the scope of `/code all`.

tests: uv run pytest -q


## What a code task does here

A task described in Telegram runs in a `git worktree` beside this repo, with a shell,
so it can run the tests and iterate. The brain does the git, re-runs the test command
itself rather than trusting the model's word, and hands back a branch and a diff.

**Nothing is ever merged without a human.** A run that goes green opens a PR; a run
that fails, or that the model could not finish, comes back to the chat for a reply.
The model's environment holds no credentials, so it cannot reach a remote at all.

## Keys this file may set

- `tests:` the command that verifies a change. It must start with `uv`, `pytest`,
  `npm` or `make`. No entry means the brain reports "tests not run" rather than
  guessing a runner, and a change that was never verified is never shipped
  unattended.
- `base:` the branch to cut work from. Omit it to use whatever is checked out,
  which is usually what you want.

See `docs/ARCHITECTURE.md` D22 in the brain for the reasoning.
