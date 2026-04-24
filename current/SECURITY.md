# Security Policy

## Supported Versions

| Version | Supported          |
|---------|-------------------|
| 0.5.x   | ✅ Current         |
| < 0.5   | ❌ Not supported   |

## Reporting a Vulnerability

If you discover a security vulnerability in BioPipe-CLI, **please do not open a public issue**.

Instead, email: **security@biopipe.dev** (or open a private security advisory on GitHub).

We will:
1. Acknowledge your report within 48 hours
2. Provide an estimated timeline for a fix
3. Credit you in the security advisory (if desired)

## Security Model

BioPipe-CLI's threat model assumes:
- The LLM is **untrusted** — every output passes deterministic validation
- Plugins from third parties run in **WASM sandboxes** with zero OS access
- Session data is validated on restore to prevent injection attacks
- Cloud model endpoints are blocked by default (local-only enforcement)

See [SECURITY_AUDIT.md](SECURITY_AUDIT.md) for the full Red Team audit results.
