# Ink Studio

A free, open-source embroidery design companion for [Inkscape](https://inkscape.org/)
and [Ink/Stitch](https://inkstitch.org/). Ink Studio runs on your computer and opens
its editor in your web browser.

## Features

- Draw and edit embroidery designs, import SVG artwork, and trace images.
- Add lettering and work with embroidery fonts and thread palettes.
- Preview stitches, check designs, and export PES and other embroidery formats.
- Create PDF worksheets and save editable project backups.

## Requirements

- **Ink/Stitch 3.3.0** and an Inkscape installation.
- A modern web browser.
- **Windows:** 64-bit Windows 10 (1809 or later) or Windows 11. Application
  dependencies are included in the installer and portable package.
- **Linux:** runs from source with the dependencies in the
  [Linux setup guide](packaging/README.md#linux).

## Installation

### Windows

1. Install Inkscape and [Ink/Stitch](https://inkstitch.org/docs/install-windows/)
   if they are not already installed.
2. Run the Windows installer, or extract the portable ZIP to a writable folder
   and run `Ink Studio.exe`.
3. Open Ink Studio and follow **Setup and Diagnostics** to check your tools
   and choose where to save projects.

Setup can prepare a private Inkscape copy if your installed version lacks image
tracing. See the [installation guide](packaging/INSTALL.txt) for offline setup,
upgrades, backups, and troubleshooting.

Windows preview builds are currently unsigned.

### Linux

Follow the [Linux setup guide](packaging/README.md#linux) for native installation,
launch commands, and optional container deployment.

## Documentation

- [Installation and troubleshooting](packaging/INSTALL.txt)
- [Building from source](packaging/README.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Privacy](PRIVACY.md) and [Code signing policy](CODE_SIGNING_POLICY.md)

## License

Ink Studio is an independent companion to Inkscape and Ink/Stitch, licensed under
**GPL-3.0-or-later**. See [LICENSE](LICENSE) and [third-party notices](NOTICE.txt).
