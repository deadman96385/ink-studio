# Building and running Ink Studio

Ink Studio shares its editor and backend between Windows and Linux. Release
versions are defined in `VERSION`. For installation and troubleshooting, see
[INSTALL.txt](INSTALL.txt).

## Windows builds

Build on Windows x64 with Python 3.11+ and pip, the Windows .NET Framework C#
compiler, and Inno Setup 7. The build does not require installed Inkscape,
Ink/Stitch or the editor's development dependencies.

```powershell
# Download the pinned installer compiler and verify its checksum and publisher.
.\Build-Studio-Windows.ps1 -Python python -BootstrapTools

# Or use an installed compiler.
.\Build-Studio-Windows.ps1 -Python python -Compiler 'C:\Program Files\Inno Setup 7\ISCC.exe'

# Rebuild using previously verified cached inputs.
.\Build-Studio-Windows.ps1 -Python python -Offline
```

`-CacheDir` selects the download cache; `-Output` selects the artifact directory.
The defaults are `.native-runtime/packaging/` and `dist/`. Intermediate files go
under `build/`. Build dependencies and corresponding sources are pinned by hash
in `packaging/windows/requirements.lock` and `sources.lock.json`.

The build produces:

| Artifact | Contents |
| --- | --- |
| `InkStudio-VERSION-windows-x64-setup.exe` | Current-user Windows installer |
| `InkStudio-VERSION-windows-x64-portable.zip` | Extract-and-run package |
| `InkStudio-VERSION-source.tar.gz` | Matching application and build source |
| `InkStudio-VERSION-third-party-sources.zip` | Dependency sources and provenance |
| `SHA256SUMS.txt` | Artifact hashes |
| `release-manifest.json` | Version, source identity and artifact metadata |

Windows packages include Python and application dependencies. They reuse an
existing Ink/Stitch installation. Compatible Inkscape can be selected locally or
prepared from the pinned vendor archive through Setup and Diagnostics.

The installer keeps program files under `%LOCALAPPDATA%\Programs\Ink Studio`
and user state under `%LOCALAPPDATA%\Ink Studio`. Portable packages keep state
beside the launcher. `STUDIO_STATE_HOME` selects an isolated state folder.

## Verification

```sh
python packaging/audit_public.py --tracked
python packaging/verify_release.py --report dist/verification-summary.json
```

`packaging/public-files.json` defines the reviewed source selection. Both package
staging and source archives use it; projects, settings and local build outputs
are excluded. Distribute both matching source archives alongside the binaries.

Current Windows builds are unsigned previews. `verify_release.py --public`
rejects them; trusted-signature verification is not available in this toolchain.
See the [code signing policy](../CODE_SIGNING_POLICY.md).

The GitHub Actions workflow checks Windows and Linux and provides a manually
dispatched Windows preview build. Distribute approved packages as GitHub Release
assets, with download links in the repository README. See
[CONTRIBUTING.md](../CONTRIBUTING.md) for unit and real-engine tests.

## Publishing a preview release

1. Update `VERSION`, changelog, and versioned download links in the repository
   README. Commit the reviewed source and push it to `main`.
2. Run the **Checks** workflow manually for that revision. Wait for Windows/Linux
   checks, the Windows build, and the artifact audit to pass. Record the run URL
   and its full source commit SHA.
3. Download `ink-studio-unsigned-preview` from that specific run into a separate
   staging directory. Run `packaging/verify_release.py --dist STAGING_DIRECTORY`.
   Verify the source archive matches that commit, its content hash matches the
   release manifest, and the package version matches `VERSION`.
4. Create a draft GitHub Release with tag `vVERSION` targeting that exact source
   commit. Attach the installer, portable ZIP, matching application source archive,
   third-party source archive, `SHA256SUMS.txt`, `release-manifest.json`, and
   `verification-summary.json`.
5. Label unsigned builds as **unsigned previews**, include requirements and the
   successful build URL in the release notes, and publish as a prerelease.
   Verify the public release assets and their checksums before sharing the links.

The build workflow does not publish automatically. Signed release status still
requires the signing policy and trusted-signature verification; publishing an
unsigned preview does not satisfy those gates.

## Linux

Native Linux needs Python 3.11+, Inkscape 1.4+ with its Python extension libraries,
Ink/Stitch 3.3.0, a C compiler, and the packages in `native/requirements.txt`.
Advanced operations also need Pango/HarfBuzz, Cairo, Poppler's `pdftoppm`, and
an X11 display or Xvfb.

```sh
python3 -m venv .venv
.venv/bin/pip install -r native/requirements.txt
STUDIO_PYTHON="$PWD/.venv/bin/python" sh packaging/linux/ink-studio --check
STUDIO_PYTHON="$PWD/.venv/bin/python" sh packaging/linux/ink-studio --port 8801
# Open http://127.0.0.1:8801/
```

For nonstandard installations, use `--configure` with `--inkscape`, `--inkstitch`
and `--data` to save tool and folder choices. Native Linux uses XDG configuration,
data and state directories. The launcher builds its engine adapter in the user's
cache; source can be read-only. Use `xvfb-run -a` before the launcher on a host
without a graphics session.

`packaging/linux/ink-studio.desktop` is a desktop-entry template. Install the
launcher on PATH and `native/icon.svg` as `ink-studio.svg` for desktop integration.

### Containers

Run from the repository root:

```sh
docker build -t web-ink:3.3.0 .
docker compose --project-directory . -f packaging/linux/compose.yaml build native
docker compose --project-directory . -f packaging/linux/compose.yaml up -d native
# Open http://127.0.0.1:8801/
```

The example binds to loopback and stores projects under `designs/native/`.

## Service configuration

The local service validates Host and Origin. `STUDIO_ALLOWED_HOSTS` can list
explicit trusted proxy/LAN hosts; `STUDIO_DESKTOP_URL` supplies an optional desktop
proxy URL. Remote access requires authentication at the proxy. See
[SECURITY.md](../SECURITY.md).

Optional Respira links use `STUDIO_RESPIRA_URL`. With no URL configured, the
editor shows general machine-file transfer instructions.
