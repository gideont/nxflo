# Nexusflow static website

Edit page content in the root HTML files. Every page includes the same header
with `<!-- include:site-header -->` and footer with `<!-- include:site-footer -->`.
Change the top logo or menu once in `lib/header.html`. Change footer content,
contact details, and the Vancouver graphic once in `lib/footer.html`.
Shared header and footer styling lives in `styles.css`; avoid page-specific overrides.

`lib/site.py` expands both templates and sets the active navigation section using
`lib/seo.py`. Service detail pages highlight Services. It also versions stylesheet
and script URLs when their contents change.
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

Docker builds the HTML from the shared templates and publishes only static site
assets. Verify at `http://127.0.0.1:9001/` and `https://www.nxflo.com/`.

Run shared rendering checks with `python3 -m unittest discover -s tests`.

Search titles, descriptions, canonical URLs, social previews, structured data,
and indexability are defined once in `lib/seo.py`. Every root page includes
`<!-- include:site-seo -->`. The build and preview generate `robots.txt` and
`sitemap.xml` from the same page registry; register any new page there.
Restart the source preview server after changing the Python metadata registry.
Production uses `https://www.nxflo.com/` as the canonical origin. Docker's
`nginx.conf` redirects the bare domain and `/index.html`, and keeps missing URLs
as real HTTP 404s. See [docs/seo.md](docs/seo.md) for the audit, target pages,
and Search Console follow-up.

Run `python3 tests/check_services.py` with Playwright to check the six service
pages, native FAQ controls, and desktop/mobile layout. It supports `--url`,
`--browser-executable`, and `--screenshots` like the other browser checks.
Run `python3 -m tests.check_deployment --url http://127.0.0.1:9001 --alias-header`
to verify the served source, sitemap, robots file, redirects, compression, and
404 behaviour. Omit `--alias-header` when checking the public HTTPS site.

For the browser regression check (requires Playwright and Chromium), run
`python3 tests/check_navigation.py`. It keeps native scrollbars visible and
checks long/short page navigation at desktop and mobile widths. Use `--url`
to check another deployment and `--browser-executable` for an existing Chromium.

Run `python3 tests/check_home_cards.py` to verify arrow clicks, exclusive expansion, keyboard, touch,
and responsive challenge cards. It accepts the same browser and URL options,
plus `--screenshots /tmp/nxflo-home-review` for visual review.

Run `python3 tests/check_footer.py` to compare footer content and styling across
all pages, check keyboard access and touch targets, and catch mobile overflow.
It accepts the same browser and URL options, plus `--screenshots /tmp/nxflo-footer-review`.

### Private website analytics

See [ARCHITECTURE.md](ARCHITECTURE.md) for collection, SQLite schema, metric definitions, dashboard freshness, retention, and backup behavior.

Open `https://www.nxflo.com/admin.html` (or `/admin`) and sign in with the configured `BMS_OWNER_EMAIL` Google account. Google One Tap and the Google sign-in button reuse the portal's existing OAuth client and server-verified session. No public navigation link is added. The public login shell contains no analytics; the reporting API requires an active owner session, including for direct requests.

The Analytics tab shows daily visitors and page views for the last three or six calendar months, with separate lines for the top pages (eight by default), a ranked legend, and per-page daily CSV export. The top-page count is configurable from 1 to 20 and saved in SQLite across sessions and browsers. Dates use `America/Vancouver`. Collection began when analytics was first deployed; charts, tables, and exports omit dates before collection began and grow daily within the selected rolling window. Today's counts are partial. Page views count public document loads; visitors count distinct browsers each day, deduplicated across pages.

Collection runs from shared `script.js` and posts only the page path (no query strings, form contents, file data or referrers). A first-party, HttpOnly, Secure, SameSite cookie identifies the browser for counting, and only a daily HMAC is stored in SQLite. No IP addresses or raw browser IDs are stored in analytics tables. Daily records are retained for 400 days in the existing persistent `nxflo-bms-data` Docker volume and are included in existing database backups. Standard webserver access logs are separate from these analytics records. Cookie clearing, blocking, multiple devices and JavaScript blocking affect accuracy. Owner visits to public pages count, including while signed in. Admin pages, known bots, DNT and GPC are excluded; automated traffic can still evade detection. Collection is rate-limited by nginx.

Run `tests/test_analytics.py` with the API dependencies installed for access-control, daily counting and persistence checks. `tests/check_analytics.py [base-url]` exercises the admin with synthetic test responses at 1440, 375, 320 and 430px; it never injects demo records into production.

### Private Doc Generator

The owner admin includes a saved document form, real LangGraph generation workflow, and private PDF/HTML downloads. The API and separate `nxflo-generator-worker` share the persistent data volume. Put `OPENROUTER_API_KEY` in the ignored `.env`; both containers receive it during deployment. See [docs/article-generator.md](docs/article-generator.md) for source processing, Batch timing, review passes, billing, and operations.
