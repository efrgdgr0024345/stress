# What GitHub and serverless workers can do for this project

GitHub stores the source and runs automated checks through **GitHub Actions**.
DigitalOcean Functions runs an actual processing job when invoked. The website
accepts uploads, retains project data and displays results. They have different
roles; a green GitHub test does not mean a live cloud service is deployed.

| Task | GitHub Actions | DigitalOcean Functions |
| --- | --- | --- |
| Test a code change before release | Yes: automated on pushes/PRs | Can smoke-test the deployed version |
| Read our public sample PDF and compare outputs | Yes, in a disposable runner | Yes, when explicitly invoked |
| Check memory, package size, input rejection and source hashes | Yes, with a declared test profile | Must additionally qualify real platform behaviour |
| Build and deploy a worker | Yes, with a secure provider connection | Hosts the deployed function |
| Keep the website and project database online permanently | Not a production application host | Not a persistent database/filesystem |
| Prove every engineering dimension or OCR word is correct | No | No |
| Run arbitrary Windows/CAESAR software without licensing or runtime support | No | No |

## How the demo works

The developer pushes code → GitHub builds the function ZIP → a resource-limited
container processes the included real PDF → checks inspect typed evidence and
material proposals → a small JSON test report is retained. No DigitalOcean token
is needed for that qualification job. The actual deployment workflow requires a
secret, repeats those checks, deploys the private function, invokes it and checks
the real provider responses.

GitHub tests can catch broken imports, missing dependencies, lost edits, stale
workers, invalid geometry handling, corrupt exports and many regressions. They
can open the website in a real browser, download/reopen Excel and PDF files,
simulate failures and inspect original source integrity. Source fixtures,
expected results and coverage determine what the tests actually prove.

The tests cannot prove unseen drawings are correctly interpreted, establish
engineering approval, guarantee immunity to every malicious file, reproduce
every hosting provider or predict an invoice from one local timing result.
External CAESAR application import still needs a real round trip. Current OCR
rows remain proposals, and unknown geometry/material properties remain unknown.

## Useful serverless jobs

Good candidates include bounded page OCR/extraction, thumbnail creation, report
generation, file validation and background conversion. Each job needs explicit
inputs, results, deadlines and safe retry rules. Serverless is less suitable for
persistent databases, an always-open desktop, jobs beyond platform time/memory
limits, or treating a temporary filesystem as permanent storage.

The provider still runs computers and Linux internally. We avoid maintaining a
dedicated OS and paying for an idle VM; dependencies and application code still
need testing and maintenance. Root access is not necessary for this Functions
demo. Provider isolation also does not imply the parser has no network access.

## Keeping costs predictable

Use a bounded per-page job, avoid idle polling, limit retries/concurrency and
record duration and memory. Begin with the included allowance, but do not assume
it is unused across the whole account. Storage, transfer and taxes are separate.
Standard GitHub-hosted runners for public repositories are generally free;
private-repository allowances, larger runners and artifact/cache storage depend
on the account plan. This demo retains small reports for seven days instead of
publishing every large native dependency bundle as an artifact.

See [the private function demo](../serverless/digitalocean/README.md) for commands,
scope, limits, account connection and the distinction between local qualification
and a successful live deployment.

## Connect from the website (0.4.5)

The hosting administrator can open **Admin connections** in the left sidebar,
paste a DigitalOcean personal access token, and select **Save & test connection**.
The token needs Functions read, create and admin permissions. The application
tests namespace-list access before saving or replacing the credential; create
and deployment permissions are additionally exercised by the worker demo.

The token is stored in `CAESAR_DATA_DIR/providers/digitalocean/credentials.json`
with owner-only permissions (0600), beneath private directories (0700), outside
the public website and the replaceable application installation. It is not
returned by the API, stored in browser localStorage, added to GitHub, sent to the
PDF parser, or included in diagnostic events. This is a private server file,
not encryption at rest or an external secret manager. The hosting account owner
and its backup operator can read it. Automatic code updates preserve it.

Select a project, active source PDF and region, then **Deploy & test worker**.
The existing separate cron runner advances recorded build, namespace, private
deployment, invocation, result polling and workbook stages. It uses the provider
REST APIs; `doctl`, root access, a VPS and GitHub secrets are unnecessary for this
website route. Requests are bounded, credential-bearing redirects are rejected,
and an interrupted ambiguous invocation is not automatically repeated.

The demo copies one PDF up to 700,000 bytes and processes its first two registered
pages. Results appear as an unreviewed materials table with editable XLSX, CSV
tables and a small diagnostic report. It does not rewrite the project's drawing
or accepted engineering data. The most recent demo is retained; starting a new
one replaces the previous demonstration copy and downloads. Temporary build
files and the namespace capability are removed after successful completion.
The private provider namespace/function remains for reuse; removing the saved
token does not delete provider resources or revoke that token at DigitalOcean.

Functions includes 90,000 GiB-seconds per team per month; additional compute is
US$0.0000185 per GiB-second. Two 1 GiB invocations at their full 240-second limit
cost US$0.00888 in compute before unused allowance and tax. Retries add usage;
account-wide allowance consumption, transfer and current provider pricing must
still be considered. This demo creates no Droplet, database, bucket or schedule.
Normal large-file uploads still use the existing hosting worker; extending the
provider adapter into general production transport remains separate work.

Provider diagnostics (0.4.6) record HTTP status, method, resource category, response
size/types, timing and the provider request ID when available. Search `provider.`
in Logs to follow connection, deployment, activation and page-completion events.
Neither raw provider responses nor uploaded function/PDF bodies are logged.
An empty namespace list may be null; deployment credentials are obtained from
the full namespace detail endpoint rather than redacted list summaries. A
successful action PUT is acknowledged without reading its large binary echo.
