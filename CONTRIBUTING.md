# Contributing

Thank you for your interest in contributing to flightdata2.

## How to contribute

All contributions must go through a **pull request**. Direct pushes to `main` or `master` are not accepted.

### Workflow

1. Fork the repository or create a feature branch from `develop`.
2. Make your changes and ensure all tests pass:
   ```bash
   uv sync --group dev
   uv run ruff check
   uv run python -m pytest tests/ -v
   ```
3. Open a pull request against `develop` with a clear description of what was changed and why.

### Review

All pull requests are reviewed by [@tnptm](https://github.com/tnptm). Please allow reasonable time for a response. PRs without passing tests or with ruff violations will not be merged.

### Code style

- Follow the conventions described in `.github/copilot-instructions.md`.
- Run `uv run ruff check` before committing. Fix all reported issues.
- Do not add unnecessary comments, docstrings, or abstractions.

## Reporting issues

Open a GitHub issue with a clear description, relevant log output, and steps to reproduce.
