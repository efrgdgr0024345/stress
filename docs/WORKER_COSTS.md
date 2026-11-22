# Low-cost processing: DigitalOcean research

Checked 22 November 2026; prices below are **USD**, excluding tax, storage,
transfer and external OCR/vision services. No paid infrastructure was created.

## Recommendation

Keep the existing cPanel website. Do not buy an always-on VM at this stage.
Start with native/vector extraction and a bounded, provider-approved cron job
on existing hosting where practical. This is not a parser isolation solution.
For heavy OCR, the best first managed-container candidate is an **App Platform
scheduled job**, which is billed only while running and supports Dockerfile
builds. It can poll for work, process a bounded batch and exit; the documented
minimum schedule interval is 15 minutes, so account for queue delay. Benchmark
**DigitalOcean Functions** for lightweight burst extraction/free allowance.
OCR is implemented and tested in the local isolated worker; remote dependencies, job-only app
configuration and actual billing/capacity must be verified before provisioning.

| Option | Published cost/limits | Decision |
| --- | --- | --- |
| Existing cPanel cron | No new DigitalOcean compute bill; hosting quotas/cron policy still apply | Small bounded jobs only; do not run long work in Passenger |
| Functions | 90,000 GiB-seconds/team/month free; excess $0.0000185/GiB-second; minimum 100 ms/invocation | Best first DO candidate for intermittent, bounded extraction |
| App Platform continuous worker | Size pricing starts at $5/month for 512 MiB; 1 GiB fixed plan $10/month | Avoid an idle worker for a small pilot; 512 MiB may be inadequate |
| App Platform scheduled job | Billed for running time only, not idle intervals; minimum schedule every 15 minutes | Preferred container candidate for heavier OCR; use a short poll-and-exit job and confirm selected-size minimum billing |
| VM/Droplet | Operational overhead and provisioned-resource cost | Not selected for this pilot |

Functions limits: 15-minute execution including initialization, 128 MB–1 GB
memory, 48 MB built-function size, 1 MB input and response payloads, no durable
local storage. A complete Tesseract/native dependency bundle may not fit.
Cold starts, real-page memory and OCR binary availability must be benchmarked.
Do not describe Functions as a proven full OCR host yet.

Use one page or a bounded page batch per job. Pass a job ID and short-lived
scoped file access, not a PDF in the invocation payload. Keep originals/results
on private existing storage. Never provide account/admin credentials to parsers.
Function isolation does not establish a no-network parser sandbox by itself.

## Illustrative compute costs

`max(0, invocations × allocated GiB × seconds − 90,000) × $0.0000185`

- 1,000 invocations × 0.5 GiB × 60 s = 30,000 GiB-s: $0 compute if the shared
  team allowance is otherwise unused.
- 10,000 of those invocations = 300,000 GiB-s: approximately $3.89 compute.
- 1,000 invocations × 1 GiB × 600 s = 600,000 GiB-s: approximately $9.44.

These are examples, not forecasts. Retries and other team functions consume the
same allowance. No promise of zero total cost or an automatic provider spending
cap is made. Begin with concurrency 1, per-project page/job quotas, bounded retry
counts and runtime caps; measure actual work before selecting paid capacity.
Billing alerts should supplement application limits, not substitute for them.

## Official sources

- [Functions pricing](https://docs.digitalocean.com/products/functions/details/pricing/)
- [Functions limits](https://docs.digitalocean.com/products/functions/details/limits/)
- [App Platform pricing](https://docs.digitalocean.com/products/app-platform/details/pricing/)
- [Scheduled jobs: billing and minimum interval](https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/)
- [Functions pricing examples](https://www.digitalocean.com/pricing/functions)

The current implementation includes durable queued jobs, a tested local Docker
parser/OCR adapter, optional Landlock/seccomp and an explicitly selected bounded
cPanel pilot mode. No remote DigitalOcean worker/account has been created or
billed. A cross-host scoped job/file transport and representative cost benchmark
remain required before moving drawings there. See [worker setup](PROCESSING_PIPELINE.md).
