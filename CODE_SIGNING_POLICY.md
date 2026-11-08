# Code signing policy

Windows preview packages are currently unsigned. Publisher signing is not active,
and SignPath Foundation approval has not been granted. Checksums verify file
integrity; they do not establish publisher identity.

## Release policy

- Only Ink Studio's launcher, engine adapters and installer may be signed under
  the project's identity. Third-party components retain their upstream identities.
- Release executables must identify Ink Studio and carry the release version.
- Signed releases require verifiable GitHub-hosted builds, explicit maintainer
  approval, and verification of certificate trust and timestamps.
- Repository and signing access require MFA. Build and signing changes require
  maintainer review.

[@deadman96385](https://github.com/deadman96385) maintains the project, reviews
contributions and approves releases.

If SignPath Foundation signing is approved, signed release pages will include:

> Free code signing provided by SignPath.io, certificate by SignPath Foundation.

See [Security](SECURITY.md) and [Privacy](PRIVACY.md).
