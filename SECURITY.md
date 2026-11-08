# Security

Ink Studio normally runs a local HTTP service on loopback. It can access your
selected project folder and installed embroidery tools. Host/origin validation
blocks unrelated browser requests; it is not authentication for a public network.
Remote use requires a deliberately configured trusted, authenticated proxy.

Report vulnerabilities privately through the repository's Security tab when
private reporting is available. If it is unavailable, open an issue requesting a
private contact route without including vulnerability details, designs or logs.
Do not post credentials or unreviewed local files in a public issue.

Exported diagnostics exclude designs, personal paths and raw logs. Detailed local
logs are separate and may contain paths. See [Privacy](PRIVACY.md).

Preview builds are unsigned. Do not treat checksums as publisher authentication.
The project's [code signing policy](CODE_SIGNING_POLICY.md) describes the intended
signing process and its current status.
