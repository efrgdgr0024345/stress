# One-command cPanel setup for easyai.com.au/stress/

Run `scripts/install_cpanel.py` with your account's Python 3.12 in **cPanel
Terminal**. Download it to a file first; do not pipe it into Python, because it
may need to prompt for credentials or the public folder's filesystem path.
No root, sudo, git, Docker or Node.js is required on your hosting account.

The script changes the Python application and the routing of
`https://easyai.com.au/stress/` on the account where you execute it. It does not
connect to your hosting from this workspace. Python Selector must already be
enabled, as the account's preflight check confirmed.

```bash
caesar_setup_file=$(mktemp "$HOME/caesar-setup.XXXXXX") &&
curl -fL --proto '=https' https://raw.githubusercontent.com/efrgdgr0024345/stress/main/scripts/install_cpanel.py -o "$caesar_setup_file" &&
/opt/alt/python312/bin/python3 "$caesar_setup_file"
```

For an immutable installer, replace `main` in that download URL with its
reviewed commit SHA. The application ZIP itself is pinned to commit
`1878feb89e81320c610a43f0b3da6452283db4ef` and checked against SHA-256
`1f8378692ab99d19c8bbb9b71272ee5543658fb6a9dcc62cd5292f981becb695`.
Updating the ZIP in main does not silently change this tested release.

## What happens

1. Download and checksum-check the package and its file manifest.
2. Check existing Python apps for root/URL conflicts. Reuse a matching app;
   stop without changing a conflicting application.
3. Locate the public stress folder, or prompt for its filesystem path if
   discovery is inconclusive. Verify its URL mapping using a temporary random
   text file, then remove that file.
4. Back up the loader, lessons and `.htaccess` privately. Keep Python code in
   `$HOME/caesar-system`, outside public_html.
5. Prompt for administrator email and a hidden password if private configuration
   does not already exist. Save configuration outside the website with mode
   600. Reruns reuse credentials; this does not reset an existing password.
6. Back up existing private drawing data with the matching Python app stopped.
7. Register with CloudLinux at domain `easyai.com.au`, URI `stress`, Python
   3.12, startup `passenger_wsgi.py`, entry point `application`. Restore the
   reviewed entry point if the provider generates a starter template.
8. Install requirements through CloudLinux, update only the public loader and
   lessons, and restart.
9. Verify authenticated health, administrator login, project access and logout
   before printing **READY** and the website address.

Other public files, runtime data and private credentials are retained. If an
existing app has environment overrides, setup stops for review instead of
passing secrets through process arguments or replacing unrelated settings.

## If setup stops

Share the printed step and status message. Do not paste passwords, private
configuration contents, or raw Selector logs into chat. Failed Selector output
is saved in a mode-600 log because it may contain environment variables. The
output identifies the private backup directory.

A failed dependency installation can be retried with the same command. A
matching app is reused instead of registered twice. Changed package files are
backed up; runtime data and credentials are kept. Routing may already have
changed after registration, so a failed run is not a working deployment.

For rollback, stop the Python app and restore the saved public `.htaccess` and
loader from that run's backup; retain private data and configuration. Do not use
Selector's destroy operation as a shortcut for rollback.

If Selector refuses create/install/restart, ask the provider to enable those
account capabilities. If health never becomes ready, inspect private Passenger
logs and check memory, CPU, subprocess and dependency support.

After **READY**, open `/stress/`, sign in, upload a non-sensitive drawing, add a
node/note, export a review bundle and preview it. The installer checks service
and login readiness; it does not replace these actual-host PDF checks.

This remains a restricted engineering-review pilot. Security, backup, licensing
and production requirements in [CPANEL.md](CPANEL.md) apply. Use provider access
restrictions or a VPN for the pilot, including its API.

## Validation limits

Installer tests use a simulated Selector and an actual local HTTP test server.
They exercise first installation, reruns, backups, credential/data retention,
provider templates, dependency failure and resume, application conflicts,
malformed packages and incorrect URL mappings. Separate package tests exercise
the actual Passenger WSGI adapter, uploads and exports. This workspace is not
the user's CloudLinux server; a live installation is verified only when the
operator successfully runs the command there.

## Diagnose a health URL that returns 404

A successful Selector restart does not prove requests reach Python. If
`/stress/api/v1/health` returns a web-server HTML 404 and `/stress/` still serves
an existing PHP site, inspect URL routing and the directory index before
assuming dependency or memory failure. The installer now reports this case
separately instead of repeating startup waits.

Download and run `scripts/diagnose_cpanel.py` with the account's Python 3.12.
It reports only selected Passenger/index directives, existing index filenames,
HTTP statuses/titles and isolated WSGI startup. Environment variable values and
rewrite arguments are omitted; configured secrets are redacted from exception
output. WSGI initialization uses a temporary private database and leaves real
projects, credentials, routing and existing PHP files intact. Review output
before sharing; do not share the private configuration or full server logs.

## Updating the forked-worker startup adapter

The currently pinned package initializes its ASGI adapter inside each serving
worker, rather than creating a background event loop before fork. See
[worker fix and reproduction](CPANEL_WORKER_FIX.md). Rerunning the latest
installer preserves existing credentials and data and backs up replaced code.
For unavailable hosting health, it invokes the checksum-pinned scoped routing
repair, then verifies login again. Access restrictions and login failures do
not trigger routing changes. Use the final setup status after all recovery
steps finish; the actual host remains unverified until those checks succeed.

Release 0.3.1 retains the administrator System updates panel and cron setup, adds Logs and real reviewed-drawing regressions, and enables notes-only review export. Existing 0.3.0 installations can install it through System updates. See [update/rollback policy](SYSTEM_UPDATES.md), [logging](LOGGING.md), [real drawing evidence](REAL_DRAWING_VALIDATION.md) and [DigitalOcean cost research](WORKER_COSTS.md). Automatic installation is off until explicitly enabled.
