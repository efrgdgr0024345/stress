# GitHub updates and rollback

Administrators have a **System updates** panel: Check GitHub, Install update,
Roll back, and optional automatic compatible updates. Other users cannot call
the update API. Auto-install is off by default. A cPanel cron runner performs
installation independently of Passenger; no extra VM or background web thread.

The one-time hosting installer configures a five-minute cron schedule through
`scripts/enable_updates.py`. If crontab is unavailable, use its printed schedule
in cPanel Cron Jobs. The panel requires a recent runner heartbeat. The existing
hosting account must permit cron; lack of that permission is not a working
automatic installation. The initial upgrade still needs a terminal command
because the deployed older app has no updater.

## Release contract

`updates/stable.json` is the repository owner's stable release feed. A check
resolves GitHub main to an immutable commit, then pins its feed and ZIP to that
commit. Only the fixed repository is accepted. Raw branch code is not executed.
SHA-256 package and per-file manifest checks, archive expansion/path checks,
release identity, schema 2 and identical Python requirements are mandatory.
The repository owner is a trusted software publisher. Hashes protect integrity;
they are not independent signatures against a compromised GitHub account.

Only explicitly code-compatible releases qualify. Dependency changes and
database migrations are refused and require a separately planned manual update.
Do not mark a destructive schema change compatible. Run CI and bump RELEASE.json
for each publishable version, build the allowlisted ZIP, then publish its hashes
in the stable feed. Never put secrets or runtime data in the release bundle.

## Installation and recovery

Release 0.4.2 fixes a maintenance-mode check failure: the new server must allow
GET/HEAD of its public frontend and assets while the updater checks the new
release. Project requests remain blocked until installation completes. Older
servers can install this fix through the existing updater; it needs no schema
or dependency changes. A regression runs the real health-check function against
the application in maintenance mode at both `/` and `/stress/`.

The runner stages the release privately, boots it against a disposable database,
backs up SQLite consistently and retains the previous code/public frontend.
During a short maintenance window it swaps code, copies public assets, restarts
Passenger, and requires the new **import-time release ID** plus authenticated
health before success. An old serving process cannot satisfy the new version
check. Failure restores old code/public files and restarts. Manual rollback uses
the retained previous code; drawings, accounts and current data are preserved.

A journal enables recovery on the next cron tick after a terminated/crashed
activation. A missing cron service, disk failure or host outage can prevent that
recovery; keep the private backup and operator access. The update panel reports
failed/interrupted state. No claim is made that rollback recovers arbitrary
filesystem failures. The updater takes the separate pipeline runner's lock;
an active drawing job defers installation to the next cron tick, so parser code
is not replaced while in use. A long-lived local development worker should be
stopped for a code update; cPanel runners are bounded and release the lock.
SQLite snapshots are retained for operator recovery but
are **not** automatically restored over newer project edits. This is why schema
and dependency changes are excluded from automatic updates.

Retain backups until the updated system is verified, then remove older private
backups according to your retention/storage budget. Monitor free disk space.
The existing engineering/security pilot limitations remain; an updater does
not establish final engineering approval, provider OS visibility or production
security. See [current worker protections and hosting setup](PROCESSING_PIPELINE.md).
