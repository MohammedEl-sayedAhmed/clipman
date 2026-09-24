# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.2.x   | :white_check_mark: |
| < 1.2   | :x:                |

## Supported Platforms

Security fixes target the documented support window:

- Python 3.10–3.14
- GNOME Shell 45–51 through the bundled extension; the app baseline is
  Ubuntu 24.04+ with GNOME 46
- Wayland sessions. Clipman is Wayland-native and X11 is not supported

Reports about platforms outside this window are still read, but a fix
may wait for the release that widens the window.

## Reporting a Vulnerability

If you discover a security vulnerability in Clipman, please report it
privately so the project has time to release a fix before public
disclosure.

**Preferred channel:** [GitHub private vulnerability reporting][gh-report]
on this repository.

[gh-report]: https://github.com/MohammedEl-sayedAhmed/clipman/security/advisories/new

If you cannot use private reporting, email the maintainer at the
address listed in the project's `pyproject.toml` / git history. Do
**not** open a public issue for security bugs.

When reporting, please include:

- A description of the vulnerability and the impact
- Steps to reproduce (or proof-of-concept code)
- The affected version(s)
- Any suggested mitigation, if known

You can expect:

- An acknowledgement within 7 days
- A status update within 14 days
- Coordinated disclosure once a fix is available

Thank you for helping keep Clipman and its users safe.
