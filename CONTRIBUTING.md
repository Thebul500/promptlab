# Contributing to PromptLab

Thanks for your interest in contributing to PromptLab! This guide covers everything you need to get started.

## Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/your-org/promptlab.git
   cd promptlab
   ```

2. **Create a virtual environment:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install in development mode:**

   ```bash
   pip install -e ".[dev]"
   ```

   This installs PromptLab along with dev dependencies (pytest, coverage, bandit, etc.).

4. **Verify your setup:**

   ```bash
   promptlab --help
   ```

## Test

Run the full test suite with:

```bash
pytest
```

Run with coverage reporting:

```bash
pytest --cov=promptlab --cov-report=term-missing
```

Run a specific test file:

```bash
pytest tests/test_integration.py -v
```

All pull requests must pass the existing test suite. If you add new functionality, include tests that cover it.

## Pull Request

1. **Create a branch** from `master` for your change:

   ```bash
   git checkout -b feature/your-feature
   ```

2. **Make your changes.** Follow the existing code style and patterns in the project.

3. **Write or update tests** to cover your changes. Aim for meaningful coverage of new logic.

4. **Run the test suite** and confirm everything passes before submitting.

5. **Commit with a clear message** describing what the change does and why.

6. **Open a pull request** against `master`. In the PR description:
   - Summarize what the change does
   - Note any breaking changes
   - Reference related issues if applicable

7. **Address review feedback** promptly. A maintainer will review your PR and may request changes.

## Code Guidelines

- Keep changes focused — one feature or fix per PR.
- Follow existing patterns in `src/promptlab/`.
- Add docstrings for public functions and classes.
- Don't introduce new dependencies without discussion.
- Run `bandit -r src/` to check for security issues before submitting.

## Reporting Issues

Open an issue on GitHub with a clear description, steps to reproduce, and expected vs actual behavior. Include your Python version and OS.
