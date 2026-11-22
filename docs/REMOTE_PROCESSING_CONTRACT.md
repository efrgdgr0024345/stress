# Normal project processing on DigitalOcean

This is a backend adapter. Users keep one project/drawing pack, the same viewer,
review controls and exports. They never create or manage individual page jobs.

1. Authenticate and retain the immutable original PDF, its SHA and source revision.
2. Register all pages in the existing supervised parser. Split only pages about
   to run into exact single-page PDFs; retain CropBox, rotation and source streams.
3. Give each task an expiring, random capability scoped to one page source and
   its result. Store only its hash on hosting. The provider receives no account,
   session, administrator or project-wide storage credentials.
4. Invoke at most two private functions concurrently. Each handles one page with
   a 1 GiB / 240 second provider limit and bounded OCR raster sizes. Files over
   the inline JSON cap are fetched over fixed-host HTTPS, up to 30 MiB per page.
5. The source fetch claims the actual provider activation ID. Duplicate execution
   cannot claim another copy of the same page. Submission ambiguity is recovered
   from that claim; it is never silently treated as successful work.
6. Deliver compressed typed evidence to the scoped result endpoint, bounded to
   16 MiB expanded. This avoids the provider's 1 MB invocation-result cap. A
   small inline result can be a recovery path if callback delivery fails.
7. Validate source/page hashes, identity, geometry and evidence, then reconcile
   IDs back to the original multipage PDF. Fence/cancel checks precede publication.
   The source and previous engineering edits are never replaced by page files.
8. Reuse completed page evidence. Keep failures visible and bounded; do not OCR
   successful pages again to retry one failed page. Bound per-day submissions,
   attempts and temporary storage. Clean temporary page files after acceptance.
9. Continue composition, review-task preparation and native PDF/Excel drafts in
   the existing workflow. Approval remains an explicit revision-bound human act.

No new always-on server, paid database or object-storage bucket is needed for
this adapter. The existing hosting stores the private page transfers and results.
DigitalOcean compute is metered only when functions run; its team allowance is
shared. Retry limits and the daily page budget bound unexpected compute usage.

The execution ledger records implementation and actual qualification status.
This contract alone is not proof that its acceptance tests have passed.
