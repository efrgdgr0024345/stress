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
3. In **Setup Python App** select Python 3.12, production mode, private
   application root `caesar-system`, startup file `passenger_wsgi.py`, and entry
   point `application`. A domain root or a subdirectory works. For the EasyAI
   installation use domain **easyai.com.au** and application URI **stress**,
   giving `https://easyai.com.au/stress/`. Passenger maps that public URL to the
   private Python app; it must not expose the source directory as a document
   root. Keep the rest of the EasyAI website in its existing location.
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
6. Restrict the **entire application URL**, including its API, using your provider's
   private access controls or a VPN. Restart the Python application in cPanel.
   The Install button explains these steps; it does not contact your hosting
   account or execute an unattended remote installer.

## Command-line setup with CloudLinux Python Selector

For an account with Python Selector enabled, configure credentials privately:

```bash
cd "$HOME/caesar-system"
/opt/alt/python312/bin/python3 scripts/configure_cpanel.py
```

The prompt saves settings in `$HOME/.config/caesar/caesar-system.json` with mode
600, and selects `$HOME/caesar-data/caesar-system` as private data storage. Keep
this file and backups private. The configuration contains the bootstrap password
in plaintext protected by account filesystem permissions, as do many hosting
configuration systems. Never copy it to public_html or commit it. Explicit
application environment variables take precedence over this file.

Then register the app using CloudLinux's documented CLI (no password arguments):

```bash
cloudlinux-selector create --json --interpreter python \
  --domain easyai.com.au --app-root caesar-system --app-uri stress \
  --version 3.12 --startup-file passenger_wsgi.py --entry-point application
```

Before registration, back up the current public `stress` folder, particularly
its `.htaccess` and loader. Registration changes routing for `/stress/`; it does
not authorize replacing unrelated site files. If the application already exists,
do not register it twice; use its existing environment and configuration.
CloudLinux may generate a startup template; verify `passenger_wsgi.py` still
matches the packaged version before starting the app.

Python Selector can install into the application's environment directly:

```bash
cloudlinux-selector install-modules --json --interpreter python \
  --domain easyai.com.au --app-root caesar-system --requirements-file requirements-cpanel.txt
cloudlinux-selector restart --json --interpreter python --app-root caesar-system --domain easyai.com.au
```

Alternatively use the **activation command supplied by Python Selector**, not
the system Python. A common environment location is
`$HOME/virtualenv/caesar-system/3.12/bin/activate`, but confirm the actual path
on your account. After activation:

```bash
cd "$HOME/caesar-system"
python -m pip install --upgrade pip
python -m pip install -r requirements-cpanel.txt
python scripts/check_host.py
cloudlinux-selector restart --json --interpreter python --app-root caesar-system --domain easyai.com.au
```

If an older physical `loader.php` remains in the public stress folder, back it
up and replace just that file with the new loader. Keep `LESSONS_LEARNED.md`
beside it for the PHP-only fallback. Do **not** extract the Python application
or data into that public folder. The Python app itself serves its loader,
built assets and API through the Passenger URL mapping.

Reference: [CloudLinux Python Selector CLI](https://docs.cloudlinux.com/cloudlinuxos/command-line_tools/).
These commands require the hosting account's existing Selector support, not
root access. The provider's actual URL mapping, quotas and overrides still
need the verification steps below.

## Verify before using real drawings

- `https://easyai.com.au/stress/api/v1/health` must respond with `mode: authenticated`.
- Open `https://easyai.com.au/stress/`, sign in with the configured credentials, then
  visit `/stress/loader.php`. Create a project, upload a non-sensitive PDF, add a note,
  export and preview it inside the website. Restart the app and check that the
  project remains. A fresh install intentionally has no demonstration project.
- Requests for `/stress/.env`, `/stress/.git/config`, `/stress/passenger_wsgi.py`,
  `/stress/requirements.txt` and `/stress/.local/workspace.sqlite3` must not expose files.
  Check this at the actual hosting URL, since Apache configuration matters.
- The password-free `/stress/api/v1/auth/local` login must return 403. Do not expose
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
