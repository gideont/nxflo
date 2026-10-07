# Nexusflow static website

Edit page content in the root HTML files. Every page includes the same header
with `<!-- include:site-header -->`. Change the logo or menu once in
`lib/header.html`; shared header styling lives in `styles.css`.

`lib/site.py` expands the header and sets the active link from the current page's
filename. It also versions stylesheet and script URLs when their contents change.
Utility pages have no active menu link. The built header works without JavaScript.

Preview source pages with `bash 3_preview.sh` (hot reload), or run:

```sh
python3 build.py
python3 -m http.server 8001 --directory dist
```

Root HTML files are source templates; use the preview server or `dist/` to view
the complete site. Do not edit generated `dist/` files.

Build and deploy as before:

```sh
bash 1_build_docker.sh
bash 2_deploy_docker.sh
```

Docker builds the HTML from the shared template and publishes only static site
assets. Verify at `http://127.0.0.1:9001/` and `https://www.nxflo.com/`.

Run shared rendering checks with `python3 -m unittest discover -s tests`.

For the browser regression check (requires Playwright and Chromium), run
`python3 tests/check_navigation.py`. It keeps native scrollbars visible and
checks long/short page navigation at desktop and mobile widths. Use `--url`
to check another deployment and `--browser-executable` for an existing Chromium.

Run `python3 tests/check_home_cards.py` to verify arrow clicks, exclusive expansion, keyboard, touch,
and responsive challenge cards. It accepts the same browser and URL options,
plus `--screenshots /tmp/nxflo-home-review` for visual review.
