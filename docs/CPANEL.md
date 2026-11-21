# Install CAESAR on cPanel (private pilot)

The complete system needs **Python 3.12**, Passenger Python/WSGI support, HTTPS,
and permission to install Python dependencies and run PDF worker subprocesses.
The package includes the built React website; Node.js is not needed on the host.
Root or sudo access is not required: dependencies install in the account's
Python application virtual environment. Enabling Passenger itself is the
hosting provider's responsibility.
PHP-only hosting cannot run the FastAPI API. Ask your provider about Python
support before purchasing or changing hosting. This is a tested WSGI adapter,
not a claim that every cPanel plan supports it.

## Download and configure

1. Download `downloads/caesar-cpanel.zip` from the loader or GitHub. Optionally
   compare its SHA-256 with `downloads/caesar-cpanel.zip.sha256` from GitHub.
   The ZIP includes `MANIFEST.json` with hashes for all packaged files.
2. In cPanel File Manager upload and extract the ZIP in your account's **home
   directory, outside public_html**. It creates `caesar-system/`. Never place
   source files, SQLite, workbooks, passwords or original drawings in a public
   document root. Do not use an existing local-demo database for this install.
3. Create a dedicated subdomain with a valid HTTPS certificate. In **Setup
   Python App** select Python 3.12, production mode, application root
   `caesar-system`, URL at the **root of that subdomain**, startup file
   `passenger_wsgi.py`, and entry point `application`. Subdirectory mounting is
   not supported by this package. The public document root must be the empty
   `caesar-system/public` folder, with requests handled by Passenger. If your
   provider's cPanel interface cannot configure this separation, ask its support
   team to do so before proceeding. Do not point Apache at the source root.
4. Activate the virtual environment using the command shown by cPanel. From
   your application's directory, run:

   ```bash
   python -m pip install --upgrade pip
   python -m pip install -r requirements-cpanel.txt
   python scripts/check_host.py
   ```

   Alternatively use the dependency installer provided by cPanel with
   `requirements-cpanel.txt`. Installation requires your host's package access.
   Before installing dependencies you can run
   `python scripts/check_host.py --preflight` using the selected Python app's
   interpreter. A missing `passenger-config` on PATH is inconclusive; confirm
   account support in cPanel or with the provider. This check does not install
   software or change hosting configuration.
5. Add these **application environment variables in cPanel**, replacing the
   examples. Do not add them to loader.php, JavaScript, GitHub or public files.

   | Variable | Value |
   | --- | --- |
   | `CAESAR_DATA_DIR` | Absolute private path, e.g. `/home/YOUR_ACCOUNT/caesar-data`, outside public_html and the application directory |
   | `CAESAR_ADMIN_EMAIL` | Your administrator email |
   | `CAESAR_ADMIN_PASSWORD` | A unique password of at least 12 characters |
   | `CAESAR_LOCAL_DEMO` | `0` |
   | `CAESAR_SECURE_COOKIE` | `1` |

   The account needs write access to the private data path. The Passenger entry
   point refuses demo mode, insecure cookies, missing administrator settings,
   missing built assets and data inside common public/source directories.
   The administrator is created on first startup; changing these variables
   later does **not** reset an existing user's password.
6. Restrict the **entire subdomain**, including `/api/v1`, using your provider's
   private access controls or a VPN. Restart the Python application in cPanel.
   The Install button explains these steps; it does not contact your hosting
   account or execute an unattended remote installer.

## Verify before using real drawings

- `https://YOUR_SUBDOMAIN/api/v1/health` must respond with `mode: authenticated`.
- Open `https://YOUR_SUBDOMAIN/`, sign in with the configured credentials, then
  visit `/loader.php`. Create a project, upload a non-sensitive PDF, add a note,
  export and preview it inside the website. Restart the app and check that the
  project remains. A fresh install intentionally has no demonstration project.
- Requests for `/.env`, `/.git/config`, `/passenger_wsgi.py`,
  `/requirements.txt` and `/.local/workspace.sqlite3` must not expose files.
  Check this at the actual hosting URL, since Apache configuration matters.
- The password-free `/api/v1/auth/local` login must return 403. Do not expose
  the service if it accepts a login. Previously issued demo sessions are also
  rejected when demo mode is disabled.

## Troubleshooting

- **No Setup Python App:** PHP alone cannot run this application. Ask the
  provider to enable Python/Passenger or use a supported Python host/VPS.
- **503 / startup failure:** inspect cPanel's private application error log.
  Check Python version, dependencies, required variables, directory permissions
  and that the entry point is `application`. Never paste passwords into logs.
- **Cannot sign in:** HTTPS is required because hosted cookies are Secure.
  Check the email and original password used when the database was created.
- **PDF upload fails:** the hosting plan must allow subprocesses and sufficient
  memory/CPU. The parser has a 768 MB ceiling and timeout; this is not reserved
  memory. Ask the provider about Passenger workers, memory and request limits.
- **Large uploads:** configure an aggregate request limit (e.g. 35 MB) at the
  provider's reverse proxy and apply rate limits there. Application upload
  checks alone do not prevent unauthenticated request-body resource exhaustion.

## Backups and updates

Stop the Python application before backing up the **entire private data
directory**, including SQLite, sources, catalogs and exports. Store backups
privately. To update, back up first, stop the app, replace application code and
built assets from a new package, install its requirements in the virtual
environment, then restart and repeat the verification steps. Keep the data
directory separate. Do not delete it or overwrite it with a demonstration copy.

## Security and deployment limits

This package enables a **restricted pilot**, not an unrestricted public service.
Remaining security work includes isolated no-network parsers, comprehensive
active-content handling, early authenticated upload limits, application rate
limiting, stronger authentication and operational monitoring. Original PDFs are
preserved and may contain reader-dependent actions. Keep PDF readers current
and treat uploaded files as untrusted. The known PyMuPDF CLI advisory is patched
by the dependency update here; this does not certify all dependencies as safe.
Resolve PyMuPDF's AGPL/commercial licensing before a proprietary hosted release.

The package excludes runtime data, credentials, `.git`, virtual environments,
caches and node_modules. Build it from reviewed source with:

```bash
npm ci
npm run build
python scripts/package_cpanel.py
```

No cPanel installation or environment publication is performed by this build.
