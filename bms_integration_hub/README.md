# BMS Integration Hub

Portal: `https://www.nxflo.com/bms_integration_hub`

Sign in with Google using **gideont@gmail.com** to bootstrap the initial owner.
On first verified sign-in the owner is bound to Google's stable subject ID;
subsequent email changes do not transfer ownership. The app uses the configured
OAuth web Client ID and Google's official GIS button and Python token verifier.
No client secret is needed for this ID-token callback flow.

New users enter Pending approval. The owner can approve, reject, revoke, restore,
assign one role, and assign specific projects from **Users**. **Roles & permissions**
provides editable built-in roles and custom roles. Role changes show an affected
user count and require confirmation. **Access history** records administrative
changes. Only the owner can use these admin functions; roles cannot grant them.

Approved users can access only assigned projects permitted by their role.
Revocation invalidates their sessions immediately, and permission changes apply
on the next API request. Every approved user, including the owner, lands on the
project dashboard. Owner administration is under **Settings → Access management**.
The dashboard reads persisted project schedules and implementation tasks; no
example KPI counts or customer records are seeded. Requirements, architecture
and monitoring are reserved for the next project phase.
No reference/demo project data is published or seeded in production.

## Storage and migrations

The internal Python/Flask API stores SQLite in `/data/bms_hub.sqlite3` in Docker
volume **nxflo-bms-data**. The API runs as UID 10001 and has no published host port.
Nginx proxies `/bms_integration_hub/api/` to it on a dedicated Docker network.
The database and its signing key are outside the static image/web directory.

The first transactional migration creates users, roles, permissions,
role_permissions, projects, user_project_access, sessions, audit_log, and
schema_migrations. DDL is in `portal_api/migrations/001_initial.sql`. Migration 2
adds customer/site fields, lifecycle and health status, ISO start/RFS dates,
project notes and timestamps, and a project-scoped tasks table with groups,
owners, effort and planned dates. Existing accounts, roles, sessions and
project assignments are preserved. Built-in
permissions are seeded once; application restarts do not reset edited roles.
Every connection enables foreign keys, FULL synchronous mode, and a 5000ms busy
timeout. The database uses WAL. All timestamps are UTC RFC3339 strings.

The users table stores name, unique case-insensitive email, unique Google subject,
verified-email flag, approval status, one role ID, protected owner flag, creation,
update, last-login, and status-change dates plus the approving actor. Last login
means successful Google authentication, including pending or denied users.
Account sign-in never resets rejection, revocation, role, or project assignments.

Sessions use random opaque 256-bit tokens, stored only as SHA-256 hashes. Cookies
are Secure, HttpOnly, SameSite=Lax, host-only, and limited to the portal path;
sessions expire after eight hours. Mutations validate the origin and CSRF token.
Google login additionally uses a signed ten-minute browser challenge and nonce.
Google ID tokens/passwords are not stored. The owner cannot revoke/delete itself.
User accounts are retained for history rather than deleted.

## Deployment and backups

Run `bash 1_build_docker.sh`, then `bash 2_deploy_docker.sh`. Both API and website
images are built. Deployment preserves the named volume, takes a consistent
SQLite backup before migrations, starts the internal API, checks health, and
then replaces the website container. Backups are in `/data/backups/` and are
verified using SQLite's integrity check. Deployment failures do not erase the
volume. Keep backups outside this VM as part of your infrastructure backup policy.

Manual backup:

```sh
docker exec nxflo-portal-api python -m portal_api.backup /data/backups/manual-UNIQUE-TIMESTAMP.sqlite3
```

To restore, stop the API, preserve a copy of the current volume, and restore the
chosen backup as `bms_hub.sqlite3` with UID/GID 10001 and mode 0600. Remove stale
WAL/SHM files only while the API is stopped, then restart. Do not use an older
application against a newer migration version. The app refuses unknown schema
versions. Backups and restore tests must use SQLite's backup API, not a live copy
of only the main database file. Restoring a backup also restores its user/access
state; review and revoke old sessions before reopening access.

Environment: `BMS_GOOGLE_CLIENT_ID`, `BMS_OWNER_EMAIL` (bootstrap only),
`BMS_PUBLIC_ORIGIN`, and `BMS_DATABASE_PATH`. Deployment defaults to the supplied
Client ID, `gideont@gmail.com`, `https://www.nxflo.com`, and the path above.

## Interfaces

All endpoints are under `/bms_integration_hub/api`:

- `GET /auth/config` issues the Google client configuration and browser challenge.
- `POST /auth/google` verifies Google's ID token and creates a session or returns a denied status.
- `GET /me`, `POST /auth/logout` manage the current session.
- `GET /projects`, `GET /projects/{id}` enforce approval, assignment, and role permissions.
- Owner-only: `GET /admin/users`; `PATCH /admin/users/{id}` for status, role, project_ids, and an optional reason.
- Owner-only: `GET/POST /admin/roles`; `PATCH/DELETE /admin/roles/{id}`. Updates require the current version and confirmed affected user count.
- Owner-only: `GET /admin/permissions`, `GET/POST /admin/projects`, and paginated `GET /admin/audit?before={id}`.
- `GET /workspace` returns only assigned, permitted projects and tasks.
- Owner-only `POST /workspace/projects` creates project schedules.
- `PATCH /workspace/projects/{id}` requires assigned-project `planning.edit`.
- `POST /workspace/projects/{id}/tasks` and `PATCH /workspace/tasks/{id}` require the matching task permission and explicit project access.
- `GET /health` reports service/schema health without exposing account information.

The server-defined permission catalog covers project-directory view; requirements,
planning, tasks, and architecture view/create/edit/delete; and monitoring view.
Writes require the corresponding view permission. Defaults disable deletion for
all built-in roles. Project and task mutations validate dates and are audited
transactionally. Requirements, architecture and monitoring content APIs come later.

## Search exclusion and reference isolation

The portal has its own branding, no main-site navigation/footer or external home
links, and no sitemap entry. HTML and HTTP headers request noindex/nofollow;
API/static responses use no-store. Referrer policy is strict-origin-when-cross-origin
to support GIS. Do not add a robots.txt disallow that prevents reading noindex.
The original `BMS_Integration_Hub_Homepage.html` remains a local reference and is
not included in the build. Noindex is not authentication or a secrecy guarantee.

## Verification

Install `portal_api/requirements.txt` in a Python virtual environment first:

```sh
python -m unittest discover -s tests
PYTHONPATH=.:tests python tests/check_portal_admin.py --browser-executable /path/to/chromium
PYTHONPATH=.:tests python tests/check_workspace_browser.py --browser-executable /path/to/chromium
PYTHONPATH=. python tests/check_deployment.py --url https://www.nxflo.com/
python tests/check_portal.py --url https://www.nxflo.com --browser-executable /path/to/chromium
```

Browser checks require Playwright and Chromium. The admin integration test uses a
temporary database, test-only injected identity verification, and a mocked GIS
script. Neither test identities nor test authentication routes exist in the
production image. The ordinary source preview server can display the login HTML;
full authentication requires the deployed API on the same HTTPS origin.

Google references: https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
and https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid

## Dashboard implementation

`dashboard.js` centralizes JSDoc project/task models and the replaceable
`WorkspaceAdapter`. UI helpers render KPI cards, RFS tables and date-based
schedules, grouped task Gantt rows, details/editing, search and notifications.
Only API results calculate metrics. Missing dates remain unscheduled. Timelines
use UTC date arithmetic, synchronized table rows, clipped bars, internal scrolling,
and sticky identifiers. Notifications reflect current project risks/overdue RFS
plans; read acknowledgements and sidebar preference are browser-local per user.
`dashboard.css` is scoped to the authenticated shell, preserving the approved
login. Lucide 0.468.0 icons are served locally from a subset SVG sprite with its
license; there is no runtime icon CDN or Gantt dependency.

The sidebar's right edge supports pointer/touch dragging to resize its expanded
width. The browser remembers the width separately from the collapse preference.
Focus the separator and use Left/Right arrows (10px), Home (minimum), or End
(maximum); double-click the edge to reset to 240px. Width is bounded to 180–420px
and further constrained by the viewport. On mobile the collapsed icon rail stays
compact; expand it to resize the overlay without causing page overflow.
