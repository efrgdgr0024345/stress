# Repair the confirmed /stress/ routing failure

The operator's diagnostic established:

- The installed Python 3.12 virtual environment imports the actual WSGI app.
- Its isolated internal health request returns `200 authenticated`.
- `/stress/api/v1/health` returns a web-server HTML 404.
- `/stress/` still serves an existing PHP index, while the CAESAR loader works.
- The public folder is `/home/learning/easyai.com.au/stress`; its parent has
  rewrite rules, and its own `.htaccess` has the three basic Passenger directives.

The installer also created a new code directory with mode 700. Depending on
the web-server integration, that can prevent WSGI autodetection. New installs
now grant traversal on the code root (711) while configuration stays mode 600
and drawing storage remains in a separate private directory.

Download `scripts/repair_cpanel_routing.py` to a file and run it with the
account's Python 3.12 in cPanel Terminal. It needs no root access and does not
reinstall dependencies or reset credentials.

## Changes and checks

1. Confirm the public folder matches the live loader before making changes.
2. Save exact original routing/frontend bytes and directory permissions in a
   mode-700 private backup directory, with backup files mode 600.
3. Grant web-server traversal on the code directory; keep credentials and data
   permissions unchanged.
4. Prepend a rewrite bypass matching **only** `stress` and `stress/...` to the
   domain's `.htaccess`, preserving its existing rules byte-for-byte.
5. Copy the built public frontend assets and set `DirectoryIndex index.html`
   inside stress. The old `index.php` is retained unchanged. No Python source,
   configuration, database, catalog or original drawing is copied publicly.
6. Restart and check the live authenticated API, expected frontend assets and
   main-domain status. If needed, try explicit Passenger WSGI type/startup flags
   within the stress directory, then check again.
7. Print READY only when both the API and frontend checks pass. Failed checks,
   restart errors or Ctrl+C restore changed public files and the original code
   directory permissions. Backups remain available privately.

Keep the terminal open until completion. If the process is forcibly killed,
loses power or cannot write during rollback, manual restoration may be needed;
the script prints the backup path. It does not promise recovery from arbitrary
filesystem failures or server-level changes made concurrently by another tool.

If both routing strategies fail, restored files are retained and the provider
should inspect Python/WSGI mapping and private application startup logs for
`easyai.com.au/stress`. An isolated startup check does not test permissions or
contents of the real database, and account-level commands cannot enable missing
web-server integrations that require administrator configuration.

## Verification limits

Six regression tests simulate server responses and verify narrow path matching,
byte-exact backups, retention of the existing PHP index and private drawings,
explicit WSGI fallback, idempotence, and complete rollback on failure. They do
not emulate Apache/LiteSpeed directive handling. The provider's actual server
decides which directives it supports; the operator-run live checks determine
whether this repair succeeds there. The existing pilot security restrictions
and engineering-review limitations continue to apply.
