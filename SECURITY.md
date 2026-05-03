# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x (latest) | Yes |
| < 1.0 | No |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately via [GitHub Security Advisories](https://github.com/VrtxOmega/omega-stenographer-mcp/security/advisories/new).

Include:
- A description of the vulnerability and its potential impact
- Steps to reproduce or proof-of-concept code
- The version(s) affected
- Any suggested mitigations

You will receive an acknowledgment within 72 hours. If the vulnerability is confirmed, a fix will be prioritized and a coordinated disclosure timeline will be agreed upon before any public announcement.

## Scope

The following are in scope for security reports:

- **Database injection** — vulnerabilities allowing SQL injection through tool input
- **Compression bypass** — techniques causing compression to silently fail, leading to data loss
- **FTS index corruption** — inputs that corrupt or disable the FTS5 search index
- **Arbitrary code execution** — vulnerabilities in the MCP server's tool dispatch or input parsing
- **Data exfiltration** — unintended data exposure through tool responses or resources

The following are **out of scope**:

- Vulnerabilities requiring physical access to the host machine
- Attacks requiring the operator to run malicious code as the same user
- Theoretical attacks with no practical exploit path
- Issues in dependencies outside the `omega-stenographer-mcp` codebase (report those to the respective upstream projects)

## Security Architecture Notes

- All data is stored locally. No network egress occurs in stdio mode.
- The database (`steno.db`) is unencrypted SQLite. Protect it with OS-level file permissions.
- Stenographer is passive — it does not approve, block, or steer agent actions.
- The standalone script includes a venv auto-activation shim for dependency isolation.
- SSE mode exposes an HTTP endpoint. TLS termination and network access control are the operator's responsibility.

See the [Threat Model](README.md#threat-model) section of the README for explicit in-scope and out-of-scope threat boundaries.
