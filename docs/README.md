# Ink Studio visual showcase

This directory is the entire static site: HTML, CSS, a small JavaScript stitch
player, and local assets. It needs no Node packages, application server, external
fonts, analytics, or build step. It works at a domain root or a project path such
as `/ink-studio/`. The full editor still needs installed Inkscape and Ink/Stitch.

## Preview locally

From the repository root:

```sh
python packaging/verify_showcase.py
python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Open <http://127.0.0.1:8000/>. Opening `index.html` directly also shows the tour
and static preview; browser file restrictions may prevent the stitch replay.
The page remains useful with JavaScript disabled.

## Publish on GitHub Pages

1. In the repository's **Settings → Pages → Build and deployment**, choose
   **GitHub Actions** as the source.
2. Push the showcase changes to `main`, or run **Visual showcase** from Actions.
3. The workflow validates the site, uploads **only `docs/`**, and deploys it.
   Use the deployment URL shown by the workflow. For this repository the default
   project URL is `https://deadman96385.github.io/ink-studio/`.

Pull requests validate without deploying. Branches other than the default branch
cannot deploy. If the default branch is renamed, update the push branch filter.
For another static host, use this directory as the publish directory with no build
command. See [GitHub's custom workflow guide](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## Maintaining the tour

- Use the public checkout and an isolated app state/data directory for captures.
  Screenshots must show only an original, redistributable sample, never saved user
  projects, personal settings, paths, or private deployment details.
- Keep screenshots as 1280 × 720 JPEGs. Update alt text and captions if the views
  change. Images link directly to full-sized files without JavaScript; the viewer
  adds a dialog with keyboard dismissal when JavaScript is available.
- The `Field notes` sample is original geometric artwork created for this tour.
  Its SVG and screenshots are distributed under the repository's GPL-3.0-or-later
  license. `field-notes-stitches.json` contains segments decoded from its actual
  Ink/Stitch PES export. The thread SVG is rendered from those same segments.
- The replay illustrates stitch order; it does not perform digitizing or prove
  physical sewing quality. Do not describe the sample as a tested sew-out.
- Update the displayed stitch count, size, and colors if replacing the sample.
- Keep all site assets here and use relative paths. Add new reviewed files to
  `packaging/public-files.json`; binary screenshots also need explicit approval
  in `packaging/audit_public.py`.
- Run the verifier and check a desktop and narrow viewport before publishing.
  Click screenshots, dismiss the viewer with Escape, play/pause/reset the sample,
  scrub with the slider and keyboard, and follow the installation links.

No application data or engine dependencies belong in this directory.
