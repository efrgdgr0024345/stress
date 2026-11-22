# Recover the administrator login from cPanel Terminal

The hosted app uses the administrator email and password from its initial
account-private setup. Existing setup files are reused on upgrades, so an
upgrade can verify login without prompting the operator again. If those
credentials are unknown, recover them from the hosting account's terminal.

Release 0.4.1 and later include the recovery helper in the private hosting
application. Run this directly in **cPanel Terminal**, from any directory:

```bash
/opt/alt/python312/bin/python3 "$HOME/caesar-system/scripts/reset_admin.py"
```

The reset is entirely local: Python's standard library reads the account's
private database/configuration and updates the existing administrator. It does
not contact GitHub or send passwords or project data to an external service.
No root, application virtual environment or extra Python package is required.
Run it interactively, not through a pipe.

Earlier hosting ZIPs omitted this maintenance script. Those installations need
the helper copied once into the private application (for example through cPanel
File Manager), or can reuse a previously downloaded private temporary copy.
GitHub is only a way to deliver that missing file; it is not part of the reset.
If the earlier download command ran in the same terminal and its temporary file
still exists, run it again without downloading:

```bash
/opt/alt/python312/bin/python3 "$caesar_reset_file"
```

Installing a new website release is not required to use a copied helper. Keep
the script and account-private configuration outside the public website folder.

The command displays the existing administrator email. Press Enter to keep it,
or enter your preferred login email. Enter a new password of 12–1024 characters
at the hidden prompt, then confirm it. No password is printed or put in shell
history or process arguments.

Recovery updates the existing bootstrap administrator's email/password hash in
SQLite and synchronizes the private bootstrap configuration used by hosting
updates. It revokes that administrator's old sessions and records a recovery
event without passwords in the audit table. Other users, roles, tenants,
projects, drawing files, catalogs and exports are retained. Sign in at
`https://easyai.com.au/stress/` using the displayed email and your new password;
the running API reads credentials from SQLite, so no restart is required.

## Privacy and recovery limits

The private settings file must already exist with mode 600. The database must
already exist in private storage; this script does not create an administrator
in an unknown database or promote another account. Duplicate login emails and
invalid passwords are refused. It uses parameterized SQL and the application's
existing scrypt format.

Before changing credentials, the command saves the old configuration and
administrator record beneath `.config/caesar/recovery-backups/`, with directory
mode 700 and file mode 600. Those backups include sensitive authentication data:
keep them private and do not paste their contents into chat. The configuration
continues using the existing bootstrap convention of a plaintext password
protected by account filesystem permissions; this is not a complete production
security hardening solution.

Database changes run in one SQLite transaction. Configuration replacement is
atomic, and ordinary failures roll back the transaction and restore the old
configuration where necessary. A power loss/process kill between the file
replacement and database commit can still leave the two resources out of sync;
retain the private backup for manual recovery. Filesystem failure during
rollback can also require manual restoration. Keep the terminal open until the
command reports completion.

Six regressions exercise actual API login after recovery, old-session
revocation, project retention, private configuration/backup permissions,
duplicate-email and short-password rejection, rollback after a failed file
write, and no password in interactive output. These tests run against
disposable data; the hosting account must execute the command to change its
own credentials.
