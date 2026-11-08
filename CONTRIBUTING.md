# Contributing to Ink Studio

Before committing, run `python packaging/audit_public.py --tracked` and install
the local audit hooks with `git config core.hooksPath .githooks`. Review new source
paths in `packaging/public-files.json`; adding a file there does not permit user
projects, private settings, backups, credentials or generated binaries.

The shared backend and editor live in `native/`. Platform discovery and child
process ownership belong in `studio_runtime.py`; installed/portable layout lives
in `app_config.py`. Keep Windows and Linux behavior in the same shared code where
possible, with platform-specific boundaries at those modules.

Run fast checks without an engine:

```sh
python -m unittest discover -s native -p test_http_guard.py -v
python -m unittest discover -s native -p test_app_config.py -v
python -m unittest discover -s native -p test_setup_check.py -v
python -m unittest discover -s native -p test_setup_windows.py -v
python -m unittest discover -s packaging -p test_public_audit.py -v
python -m unittest discover -s packaging -p test_release.py -v
```

Use `native/verify_runtime_smoke.py` and the selected `native/verify_platform.py`
cases with real Inkscape/Ink-Stitch dependencies for engine changes. Use
`packaging/verify_windows.py` for installer/portable changes. Tests must use
disposable state, must not replace the production installer identity, and must
keep Windows engine jobs off the interactive desktop.

Build and artifact-audit instructions are in `packaging/README.md`. Keep direct
and transitive wheel hashes and dependency source hashes in the lock files. New
frontend imports must be included in the release payload. Do not package designs,
credentials, caches, developer environments or personal service addresses.

Changes to project formats need compatibility and backup/restore evidence. User
data stays outside the installed program; uninstall must retain it. Contributions
are provided under the project's GPL-3.0-or-later license, with third-party notices
retained.
