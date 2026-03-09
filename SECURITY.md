# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

Only the latest minor release receives security patches. Users should upgrade to the most recent version to ensure they have all security fixes applied.

## Reporting a Vulnerability

If you discover a security vulnerability in PromptLab, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities.
2. Email your report to the maintainers with a description of the vulnerability, steps to reproduce, and any potential impact.
3. You will receive an acknowledgment within 48 hours.
4. A fix will be developed and released as soon as possible, typically within 7 days for critical issues.

### What to Include

- Description of the vulnerability
- Steps to reproduce the issue
- Affected versions
- Any potential impact or exploit scenario

### Scope

The following areas are in scope for security reports:

- Template injection or sandbox escapes in Jinja2 rendering
- API key or credential exposure through logs, errors, or storage
- Command injection via CLI inputs
- Dependency vulnerabilities in direct dependencies
- Unauthorized access to stored prompt data or evaluation results

We appreciate responsible disclosure and will credit reporters in the changelog unless they prefer to remain anonymous.
