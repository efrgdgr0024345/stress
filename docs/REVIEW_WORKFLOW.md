# Section reviews, independent issues and account security

Release 0.5.2 adds these controls to the existing **Validation & release** page.
The project remains one drawing pack. Backend page tasks do not become a new
user-managed processing workflow.

## Engineer review

Drawing identity, materials, physical model and presentation have separate
content hashes. Available sections can be reviewed while the remaining drawing
processing continues. Open a section, inspect its source and data, record the
decision and explicitly accept any listed limitations. The application records
the person, role, time, revision, content snapshot and a private-server HMAC seal.

Accepting a material proposal marks the observation reviewed. It does not fill
missing quantities, dimensions, catalog data or manufacturer confirmation.
Unknown facts and their exceptions remain visible. Graphic bubble/leader changes
invalidate presentation review without changing physical dimensions. Changes to
physical stations/evidence invalidate the relevant physical-model review.

## Independent review issue

Every current section must be signed and processing/refresh must finish before
an independent reviewer can issue the current revision. The approver cannot be
one of its recorded preparers or section signers. Existing legacy projects may
lack historical contributor identities; current section-signature independence
is enforced and new edits record their contributors.

The reviewer needs an enrolled authenticator and a factor check within five
minutes. They must explicitly accept every outstanding exception. This creates
an **ENGINEERING_REVIEW** issue, not verified stress input. A preserved ZIP holds
the exact generated review outputs, project snapshot and sealed decision receipt.
The server checks its SHA256 and receipt/snapshot seals before download. New
edits create a draft and leave approved issues unchanged. Authenticated packet
verification is available at the approval's `/verify` API route.

Seals detect alteration relative to the private server key. They are not a
public-key certificate, external timestamp authority or independent legal
signature. Protect and back up `security/approval-key`, the database, approval
ZIPs and original files together. Losing the key blocks existing-seal validation;
the application refuses to replace a key that has already signed records.

**VERIFIED_FOR_MODELLING stays blocked** while the installed native export
profile is unqualified. Successful local tests or section signatures do not
replace actual supported PDF-editor and CAESAR application round trips. Reviewers
can record a successful external test against an exact current-revision export,
including application/version and a saved evidence reference. Such a record is
labelled a human attestation, not an automated independent test result.

## People and authenticator setup

The hosting administrator opens **People & access** to create engineer,
independent reviewer or read-only viewer accounts. Passwords require at least
12 characters. Accounts stay in the administrator's workspace; the website sends
no invitation emails. Role/access changes revoke the affected account's sessions.
Reviewers may read and approve but cannot edit or upload drawings.

Use the shield button in the top bar to open **Account security**. Enter the
current password, scan the locally generated QR code in a standard authenticator
and confirm a six-digit code. Save the ten one-use recovery codes when shown.
Neither the seed nor codes are sent to an external QR service or diagnostic log.
After enrollment, sign-in requires a factor or unused recovery code. Codes are
rate-limited and accepted counters cannot be replayed. Existing sessions retain
access; final approvals still require a recent factor check. Enrollment does not
change the existing 12-hour absolute session expiry.

Authenticator seeds and recovery-code hashes are owner-only private files,
outside the website/code directory. A database anchor prevents a missing or
replaced enabled-factor file from silently allowing password-only sign-in.
This is filesystem permission protection,
not encryption at rest. Database records, private configuration, signing keys
and sensitive recovery backups need a separately qualified backup/restore and
production storage policy. No paid MFA service or additional always-on server
is required.

Password recovery retains MFA by default. The hosting account owner can also
recover a lost administrator authenticator using the installed helper:

```bash
/opt/alt/python312/bin/python3 "$HOME/caesar-system/scripts/reset_admin.py" --reset-mfa
```

This sets a new password, disables the lost factor/recovery codes, revokes
administrator sessions and saves a private recovery backup. Enroll a new factor
before final approvals. It requires access to the existing private hosting files;
there is no unauthenticated website bypass.

The updater refuses a code downgrade to releases that would ignore enabled MFA,
disabled accounts, reviewer roles or signed-review records. The update dialog
explains when an old rollback release is no longer security-compatible. Code
rollback continues to preserve current drawings and credentials; it does not
restore an old database over later work.

## Validation boundary

Disposable API/browser tests cover enrollment, recovery/replay/rate limits,
permissions/session revocation, early section review, stale reviews, independent
approval, sealed packet integrity and preserved issues after edits. Test accounts
and approvals are synthetic. No automated test or assistant signs real engineering
work for a person. Consult `PLAN_EXECUTION.md` for remaining original acceptance
gates, including complete model generation, actual desktop qualification,
malware scanning, encryption/restore operations and original reference assets.
