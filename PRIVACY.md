# Privacy

Ink Studio runs on your computer. Projects, imported artwork, fonts, settings and
exports are stored in your selected local folders. The app has no automatic
telemetry, analytics, advertising or crash-report upload.

## Network connections

- The editor connects to its local Ink Studio service in your browser.
- Windows setup can download a compatible Inkscape archive directly from
  `media.inkscape.org`. This request exposes ordinary connection information,
  such as your IP address, to that server. Setup verifies a pinned SHA256 hash.
  A compatible installed Inkscape or a verified offline archive avoids this download.
- Documentation and optional companion-service links open when selected. Those
  sites have their own privacy policies. No personal service address is supplied
  in the public package.
- Maintainer builds download pinned dependencies from their upstream providers.
  Building the app does not upload user designs.

Ink Studio does not send your designs to Inkscape or Ink/Stitch servers to process
them; its embroidery jobs use the installed tools on your computer.

## Diagnostics and sharing

Exported diagnostics contain check codes, remedies, platform information and
numeric software versions. They omit designs, personal paths, environment values
and raw logs. Detailed logs remain local and can contain file paths; review them
before sharing. Project backups contain your artwork and should be shared only
when you intend to disclose it.

Source hosting and release downloads are provided by GitHub, whose
[privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement)
applies when you use that website. Inkscape's website and downloads are governed
by the notices published on [inkscape.org](https://inkscape.org/).
