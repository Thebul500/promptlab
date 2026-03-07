# Contributing to promptlab

Thank you for your interest in contributing to promptlab! This guide covers the development workflow from setting up your environment through submitting a pull request.

## Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/your-org/promptlab.git
   cd promptlab
   ```

2. **Create a virtual environment (Python 3.10+):**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install in development mode with dev dependencies:**

   ```bash
   pip install -e .[dev]
   ```

   This installs the project along with pytest, ruff, mypy, bandit, and other development tools.

4. **Verify the installation:**

   ```bash
   promptlab --help
   ```

## Test

Run the full test suite before submitting any changes:

```bash
pytest --cov=promptlab -v
```

The CI pipeline also runs linting, type checking, and security scanning. You can run these locally to catch issues early:

```bash
# Lint
ruff check src/

# Type check
mypy src/promptlab/

# Security scan
bandit -r src/promptlab/ -q
```

All tests must pass and all checks must be clean before a PR will be reviewed.

## Pull Request

1. **Create a feature branch** from `main`:

   ```bash
   git checkout -b feature/your-feature main
   ```

2. **Make your changes.** Follow the existing code style:
   - Line length: 100 characters (configured in `pyproject.toml` under `[tool.ruff]`)
   - Type annotations on all function signatures (enforced by mypy with `disallow_untyped_defs`)
   - No security issues flagged by bandit

3. **Add or update tests** for any new or changed functionality. Place tests in the `tests/` directory.

4. **Run the full check suite** (see the Test section above) and make sure everything passes.

5. **Commit with a clear message** describing what changed and why:

   ```bash
   git commit -m "Add support for XYZ template variables"
   ```

6. **Push your branch and open a pull request** against `main`:

   ```bash
   git push origin feature/your-feature
   ```

7. **In your PR description**, include:
   - A summary of the changes
   - Any related issue numbers
   - Steps to manually verify the behavior, if applicable

A maintainer will review your PR. Please be responsive to feedback — small iterations are easier to review and merge.

## Reporting Issues

If you find a bug or have a feature request, open an issue on GitHub. Include:

- Steps to reproduce (for bugs)
- Expected vs. actual behavior
- Python version and OS

## Code of Conduct

Be respectful and constructive in all interactions. We are committed to providing a welcoming and inclusive experience for everyone.
