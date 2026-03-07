# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | Yes                |

Only the latest minor release receives security patches. Users are encouraged to upgrade to the latest version as soon as updates are available.

## Reporting a Vulnerability

If you discover a security vulnerability in promptlab, please report it responsibly:

1. **Do not open a public issue.** Security vulnerabilities should not be disclosed publicly until a fix is available.
2. **Email the maintainers** with a detailed description of the vulnerability, including:
   - Steps to reproduce the issue
   - Affected versions
   - Potential impact
   - Any suggested fixes (optional)
3. **Expected response time:** We aim to acknowledge reports within 48 hours and provide a fix or mitigation plan within 7 days for critical issues.

## Scope

The following areas are in scope for security reports:

- **Template injection** — Unsafe variable interpolation or code execution through prompt templates
- **API key exposure** — Credentials leaked in logs, error messages, or stored insecurely
- **Dependency vulnerabilities** — Known CVEs in direct dependencies
- **Command injection** — Unsafe input handling in CLI or REST API endpoints

## Disclosure Policy

- We follow coordinated disclosure. We request that reporters allow up to 90 days for a fix before public disclosure.
- Security fixes will be released as patch versions and documented in the CHANGELOG.
- Contributors who report valid vulnerabilities will be credited in the release notes (unless they prefer to remain anonymous).
