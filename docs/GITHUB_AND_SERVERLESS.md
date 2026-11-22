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
