# DigitalOcean Functions: private OCR demo

This is a deployable **prototype**, not an already-connected website worker.
It handles one PDF page per invocation using the existing evidence extractor
and pinned PyMuPDF/Tesseract binaries. It returns OCR words with confidence,
page boxes, source hash, graphical observations and resource measurements.
Engineering stations are not inferred from pixels and no engineering approval
is conferred. The original 1010 golden fixture and canonical catalogs remain
separate, unqualified acceptance gates.

## Supported demo and limits

- CPython 3.12, Linux x86_64; configured function memory 1024 MB and timeout
  240 seconds. The child has separate CPU/time/file/address-space limits.
- Input is inline base64 PDF **up to 700,000 bytes**, expected SHA-256 and page
  index. Our user-provided 589,154-byte reviewed 1010 PDF fits the provider's
  1 MB request limit after base64 encoding. URLs, commands and output paths are
  rejected. This small-file contract is deliberate, not support for the
  website's full 30 MiB intake limit.
- Evidence is gzip/base64 inside JSON. Requests and responses are bounded
  below 1 MB; invalid, active-content and oversized inputs fail explicitly.
- Every parser subprocess starts with a clean environment. Account API tokens
  are not sent to it. The function is **private** (`web: false`); anonymous users
  cannot invoke it through a public web URL.
- Local qualification runs the exact deployment ZIP in Docker with 1 GiB RAM,
  no swap, one CPU, no network, a read-only root and no Linux capabilities.
  DigitalOcean's provider runtime is a different boundary and is labelled
  `provider-function`, not falsely described as the tested no-network sandbox.

## Build and test without a DigitalOcean account

```bash
.venv/bin/python scripts/build_functions_demo.py .local/functions-demo
.venv/bin/python scripts/qualify_functions_demo.py .local/functions-demo \
  --report .local/functions-demo/qualification.json
```

Use a fresh output directory. The builder copies an allowlisted source subset,
downloads hash-pinned wheels/model data, retains their licenses, and creates a
deterministic ZIP. No runtime data, original credentials or project database is
packaged. It refuses a ZIP over a conservative 48,000,000-byte limit.

`build-report.json` records size and dependency/artifact hashes. The qualifier
reads both actual reviewed 1010 pages and checks evidence identity, OCR coverage,
material proposals, invalid inputs and resource limits. These results establish
the local profile only; `digitalocean_live_tested` stays false.

## Secure account connection and deployment

For the website demonstration, open **Admin connections**, save the token there,
and select a small PDF project to deploy/test. This route uses the existing
cPanel runner and provider REST APIs; it needs no GitHub secret, doctl, root
access or always-on server. See [website connection and diagnostics](../../docs/GITHUB_AND_SERVERLESS.md#connect-from-the-website-045).
The GitHub/CLI deployment below is an alternative route.

Create a short-lived DigitalOcean API token with the required Functions
read/create/admin scopes and account-read access for doctl. Store it in this
repository's GitHub Actions secret named **DIGITALOCEAN_ACCESS_TOKEN**. Never put
the token in source files, shell arguments, issue text, artifacts or chat.

Run **Actions → Deploy private Functions demo → Run workflow**. An authorised
agent can also request deployment by pushing a change to
`serverless/digitalocean/deploy-request.txt` on main. That marker contains no
credentials. A marker does not bypass the secret requirement or the tests.

The workflow repeats qualification before any deployment. It creates or reuses
the `caesar-functions-demo` namespace, deploys the exact qualified ZIP, invokes
the two real source pages and publishes metadata-only evidence. Sydney (`syd1`)
is the default region. It creates no Droplet, database, Spaces bucket, public web
endpoint or scheduled trigger. Repeated manual deployments invoke the sample
again and consume function usage; this is not an unlimited free service.

For a securely configured command-line environment with doctl authenticated:

```bash
.venv/bin/python scripts/deploy_functions_demo.py .local/functions-demo \
  --region syd1 --report .local/functions-demo/live-demo.json
```

The token is read from the environment. The GitHub integration may not have
permission to create/read repository secrets; that account connection must be
supplied by the owner. Owning an account alone does not give this chat API access.
Only a successful provider smoke test sets `digitalocean_live_tested: true`.

## Live website qualification — 22 November 2026

Release 0.4.6 completed the real two-page 1010 drawing through cPanel → private
Sydney Functions → website results → editable XLSX/CSV downloads. Page one
returned 506 words / 13 material proposals in 4.307 seconds; page two returned
691 words / 19 proposals in 4.928 seconds. These are handler durations, not the
whole cron-driven workflow duration or an invoice.

The live browser displayed all 32 proposals and downloaded both formats. The
Excel reader reopened the workbook with 32 component rows, filters and frozen
headings. The original source hash and project snapshot were unchanged, and the
diagnostic export contained no provider token. See the metadata-only
[provider qualification record](evidence/provider-qualification.json).

This qualifies the small-file demonstration and its exports. Material proposals
remain unreviewed; physical geometry and a CAESAR model are not engineering
verified. Normal uploads still use the existing worker as explained below.

## What remains before normal website uploads use it

The cPanel pilot remains on its local worker until a production adapter is
implemented and qualified. That adapter needs scoped private-file transport for
larger PDFs, job IDs and leases, asynchronous invocation/recovery, result/fence
validation, tenant checks, cost/retry limits and source/evidence traceability.
Website administrator credentials must never be supplied to a parser function.
The current demo does not silently route customer PDFs to another provider.

## Costs and provider contract

DigitalOcean currently publishes 90,000 GiB-seconds per team/month included and
$0.0000185/GiB-second beyond that, with a 100 ms minimum. The allowance is shared
with other functions. Actual billing includes provider execution behaviour;
local Docker timings are not an invoice or a promise of free operation. Other
storage/transfer/tax charges and GitHub artifact quotas are separate.

Checked 22 November 2026:

- https://docs.digitalocean.com/products/functions/details/pricing/
- https://docs.digitalocean.com/products/functions/details/limits/
- https://docs.digitalocean.com/products/functions/reference/runtimes/python/
- https://docs.digitalocean.com/products/functions/reference/build-process/
- https://docs.digitalocean.com/products/functions/reference/project-configuration/
- https://docs.digitalocean.com/platform/regional-availability/
