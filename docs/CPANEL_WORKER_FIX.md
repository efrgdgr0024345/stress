# Per-worker WSGI adapter initialization

The live hosting operator reported a web-server 404, followed by 503/timeouts
when explicit WSGI routing was enabled. The backed-up routing repair restored
its prior public files after the checks failed. The app previously passed an
isolated interpreter/temporary-database startup check.

During investigation, a real fork reproduction exposed an application bug:
creating `ASGIMiddleware(app)` during startup-file import starts an event-loop
thread in that process. If the server forks workers afterwards, the inherited
adapter has no running thread and a request can hang. The original adapter's
forked request timed out under the test alarm. This is a reproduced defect,
not proof that the provider's actual 503 has this sole cause.

The Passenger entry point now constructs the adapter lazily in the serving
process, initializes its database there, checks the PID on each dispatch, and
resets cached adapter/lock state after fork. The regression makes real HTTP
requests through WSGI after both cold and warmed parent processes fork child
workers, with alarms detecting hung requests. The corrected requests complete.

## Operator update

Run the newly pinned `scripts/install_cpanel.py` with the account's Python 3.12.
It keeps the existing private credentials and drawing data, backs up prior
code/data/routing, stops the matching app, installs the corrected package and
restarts. It does not reset an existing administrator password.

If the updated app still has an unavailable health URL, the installer invokes
the previously reviewed, checksum-pinned `/stress/` routing repair, then checks
administrator login/project access again. That helper restores public files on
failure. The worker code update remains installed and its previous version is
backed up privately. Existing access restrictions and password failures are not
treated as permission to change routing. Read the final status after all steps.

If the live app still fails, preserve the configuration and obtain the private
web-server/WSGI startup error. LiteSpeed's CloudLinux support uses its own
implementation of Passenger configuration; account-level commands cannot
install missing server integrations. An isolated temporary-database check also
does not validate the real data directory under the serving worker's identity.

Reference: [LiteSpeed CloudLinux Python Selector integration](https://docs.litespeedtech.com/lsws/cp/cpanel/cloudlinux/#rubypythonnodejs-selector).
Do not run provider-level enablement scripts as an unprivileged account or
relax drawing/credential permissions. The host may need to inspect its private
startup logs if this application fix does not resolve the live failure.
