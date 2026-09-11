# M3: Email collection — implementation and acceptance boundaries

Status: classic/import collection shipped in preview **0.4.0**. Preview **0.4.1**
implements the Microsoft 365 connector and nested-forward/classic-protection fixes;
an approved Entra application ID, tenant consent and live Graph acceptance are still
pending. Packaged CI passes; evidence belongs in `PROJECT_STATE.md`.

## Implemented outcome

After checking that export emails have arrived, the user opens **3. Collect your
emailed exports** below the website controls, or uses the jump link near the top.
They choose an Inbox or saved email files, review the messages, then explicitly
download this frozen selection. Collection does not require a smaXtec login and
never requests replacement website exports automatically.

Each accepted workbook is kept as its original bytes and named using **its own**
B3 identifier. For example, one file with `203 (new girl)` becomes `cow-203.xlsx`;
another file with `257` becomes `cow-257.xlsx`. These are examples, not constant names.
No calculations, combined workbook, graphs or verified request correlation exist yet.

The screenshot says export links last **24 hours**. Forwarding the message does not
renew that lifetime, and arrival order does not establish which request a file belongs to.

## Connection decision: Microsoft 365 first, with two explicit fallbacks

| Route | Implemented user experience | Boundary |
| --- | --- | --- |
| Microsoft Graph delegated sign-in | Sign in with Microsoft 365 in the system browser, using normal organisational MFA | Implemented but not deployable until an approved public-client app ID and delegated `Mail.Read` consent are supplied |
| Classic Outlook for Windows | Connect classic Outlook, then explicitly select one available Inbox | Requires an installed/configured signed-in classic profile and permitted programmatic access; protected bodies may be unavailable |
| Saved `.eml` / `.msg` | Import saved emails selected by the user | Works independently of desktop Outlook; manual selection, not a newest-N inbox scan |

A read-only local profile check confirmed **two Inbox choices**. A later 30-day scan
inspected 445 items and found 10 recognizable export subjects, but corporate Outlook
blocked Body, HTMLBody and sender access for every mail item. Preview 0.4.0 silently
reduced that result to zero. Version 0.4.1 instead retains each recognizable subject
as a problem row explaining that its link could not be read; it never disables or
bypasses Outlook protection. No account names, store identities, message text beyond
the generic subject pattern, or links belong in this document.

Only a separate, bounded helper process imports COM and reads the user's Outlook
profile. Selecting an Inbox is mandatory; Workbench does not silently choose the
default account. It never marks mail read, moves, deletes, modifies or sends messages,
and never calls Quit on the user's Outlook. Cancellation/deadline cleanup ends only
Workbench's helper. Outlook security prompts are not dismissed or disabled.
[Outlook protected properties](https://learn.microsoft.com/en-us/office/vba/outlook/how-to/security/protected-properties-and-methods).

New Outlook does not expose the classic Object Model/MAPI interface. The Microsoft
365 connector therefore calls the mailbox service through Graph and works independently
of the installed Outlook edition. Saved-email import remains the no-Graph fallback.
[Microsoft's feature comparison](https://support.microsoft.com/en-us/outlook/getstarted/feature-comparison-between-new-outlook-and-classic-outlook).

Workbench does not collect an email password, ask users to copy authentication tokens,
or borrow Outlook Web cookies. Microsoft authentication uses MSAL's public-desktop
system-browser flow, the `organizations` authority, PKCE and `http://localhost`; the
access token and MSAL cache are memory-only and cleared on disconnect. Only delegated
`Mail.Read` is requested because message bodies are needed to recover export links;
`Mail.ReadBasic` is insufficient. No client secret belongs in a desktop app.

Every desktop OAuth application still needs an Entra application registration.
The application owner/IT must provide an approved public-client application ID,
enable the localhost mobile/desktop redirect, and grant/consent delegated `Mail.Read`
in each intended tenant. Ordinary users must not edit configuration or register apps.
Some tenant consent policies require administrator approval. The 0.4.1 source accepts
a development-only `SMAXTEC_MICROSOFT_CLIENT_ID` override; production packaging reads
the same release-controlled build variable and embeds the approved non-secret ID into
the bundle. Frozen applications ignore runtime overrides. Do not reuse an unrelated
registration without its owner's explicit approval and correct permission/redirect
configuration. A classic-Outlook result containing only `content blocked` messages is
diagnostic evidence, not an accepted collection route; Graph activation is a release
blocker in that environment.
[One-time IT setup checklist](MICROSOFT_365_SETUP.md),
[MSAL interactive sign-in](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens),
[Graph Mail.Read](https://learn.microsoft.com/en-us/graph/permissions-reference#mailread),
[consent policies](https://learn.microsoft.com/en-gb/entra/identity/enterprise-apps/manage-app-consent-policies).

Graph reads `/me/mailFolders/inbox/messages` newest-first in pages of 25, selecting
only ID, subject, sender, received time and HTML body. Every pagination URL is restricted
to the exact HTTPS Graph host/path before the bearer token is sent. Requests, response
size, page size, message/body size, total items and total time are bounded. Mail stays
read-only; tokens, Graph IDs and pagination URLs are never logged or persisted.

## Exact selection semantics

- **Latest** accepts 1–1000 matching emails, default 10; received-time lookback is
  1–30 days, default 1. Both connectors scan descending outer received time, check
  ordering, inspect at most 10,000 items and use bounded network/helper deadlines.
- N counts qualifying export messages, not arbitrary Inbox mail or guaranteed files.
  Duplicate links and problematic matches stay in the selection. A message with
  multiple different valid export links is an issue, not a guessed choice.
- The preview displays received time, sender, subject, direct/forwarded source and
  ready/duplicate/problem status as inert text. It does not render HTML, load images
  or expose URLs. Warnings cover fewer matches and scan limitations.
- **Download reviewed emails** uses exactly the immutable candidates displayed.
  Later arrivals do not change them; duplicates, failures and missing links do not
  cause top-ups. Changing Inbox/scan settings invalidates review.
- **Import saved emails** processes only selected `.eml`/`.msg` files and is labelled
  manual. Inbox Latest/lookback settings do not silently filter imports. The same
  exported message saved in both formats may resolve to the same export-link
  fingerprint and is treated as a duplicate within the resulting collection.

Direct recognition uses the actual SMTP sender `noreply@smaxtec.com` and known export
content. Inline forwarding may add any number of `Fw:` layers and rewrite prose; a
fully validated smaXtec export link is sufficient to classify it as a candidate.
A display name or quoted From text is not authentication by itself; the downloader's
constrained origin/path policy remains mandatory. Forward-as-attachment is still not
recursed automatically: save/extract the attached message and import it explicitly.

Saved MIME messages use Python's email parser; MSG uses a bounded `olefile` reader
for known root message properties and HTML/plain-text body streams. RTF and attached
message recursion are not implemented. For a forward containing an attached `.eml`
or `.msg`, save/extract that attached message and import it explicitly. Do not expand
this into arbitrary attachment extraction or silently import unrelated attachments.

## Confirmed download route and trust boundary

Supplied forwarded examples established these route shapes. No actual object
identifier is recorded: **the remote export basename itself is a bearer capability**.

| Hop | Allowed shape |
| --- | --- |
| Microsoft Safe Links, if present | Recognized `*.safelinks.protection.outlook.com` wrapper carrying the verified export destination |
| smaXtec | `https://api.smaxtec.com/api/v2/data/downloads/export-….xlsx` |
| Storage redirect | `https://storage.googleapis.com/anthilldata_excel_exports/` followed by the **same** export object |

The production allowlist is the exact host/bucket/path relationship, not all Google
storage or other cloud-hosted files. The unwrapped API URL is used only to classify
and fingerprint a Safe Links target; the actual download starts at the original
wrapper and retains its checks. Wrapper nesting, redirects, time and size are bounded.
Every hop must preserve the intended object. Unknown hosts, changed objects, URL
credentials, insecure schemes, unexpected ports and private network destinations
are rejected. No website/Microsoft cookies, credentials or tokens accompany requests.

A Safe Links warning/interstitial is not a workbook and is never clicked through.
HTML/JSON/error responses, authentication challenges, invalid redirects, unavailable
links and interrupted/oversized downloads produce curated errors. An unavailable link
is not automatically diagnosed as expired. No download or website submission retries
occur without a user action. [Microsoft Safe Links behavior](https://learn.microsoft.com/en-us/defender-office-365/safe-links-about).

Downloads have a 100 MiB compressed-file limit and 90-second overall deadline,
with short bounded network operations. Cancellation can stop waiting for system DNS;
at most one such background call may remain outstanding per downloader and it cannot
write a workbook. Its late response is discarded/closed before another attempt.

Never log, display or persist complete URLs, the remote filename/object name, raw HTTP
exception strings or response bodies. Persist only irreversible fingerprints and
curated status. The final local `cow-…xlsx` filename is safe application metadata,
not the remote capability-bearing basename.

## Workbook validation and identity

The inspector uses ZIP and hardened XML parsing, not Excel automation or workbook
rewriting. It validates package structure, CRCs, relationship paths and content types,
with limits on member count, expansion, XML size and compression ratio. No member is
extracted to an arbitrary path. Encrypted, macro/embedded/external-active or otherwise
unsupported packages are rejected.

All **visible** data worksheets must contain a supported, consistent B3 identity.
Blank/missing cells, formulas in B3, error values, conflicting identifiers and ambiguous
names fail visibly. The rules remain conservative until more schemas are reviewed.

- Text `203 (new girl)` becomes `203`; text `00203` preserves its leading zeroes.
- A supported numeric integer becomes its decimal digit identifier. Numeric cells
  cannot preserve formatting-only leading zeroes that were not stored as text.
- `203/204` is rejected, never combined into `203204`.
- Original B3 text remains in local provenance. Accepted bytes are unchanged;
  failed downloads/identification do not enter the collection as cow files.

B3 is an **animal name**, whereas website lookup uses **Animal number**. Equality is
not guaranteed. Collection does not verify farm, period, requested cow number or the
originating website batch. Future normalization/correlation requires representative
metadata samples and explicit acceptance criteria.

## Destination, duplicates and durable recovery

The default root is the OS-resolved Documents folder plus
`SmaxTec Workbench/Collections`. Browse lets each user choose another location.
The installation folder, a hardcoded username, Downloads and a particular OneDrive
path are never assumed. New collections receive unique timestamp/ID subfolders.

`cow-203.xlsx`, `cow-203__02.xlsx`, etc. preserve different workbooks for the same
identifier without overwriting. Exact duplicate export links within a collection
refer to the first successfully validated file. **New collections are independent**;
no global cache silently suppresses newly selected messages.

`application/collection_store.py` writes a SQLite journal in the per-user OS application
data location and `collection.json` in each output folder. It records collection ID,
version, ordered opaque source keys, received times, link fingerprints, saved filenames,
B3 identity, content hashes and curated statuses. Bodies, subjects, senders, account
credentials, remote basenames and bearer links are not persisted there.

Reviewed selection is journaled before work. A prepared local filename/hash is recorded
before non-overwriting atomic publication. An OS collection lock prevents concurrent
writers; completed-file hashes reconcile interrupted publication. Workbooks are not
rewritten. Normal failure/cancellation cleans incomplete staging; cleanup failure
must stay visible instead of masquerading as a completed file.

**Retry incomplete downloads** reuses the same in-memory selection/folder.
After restart, re-select the same original messages/files, review them, then choose
**Resume existing collection** and its previous folder. The same user's local journal
must exist on the same computer. Keys, fingerprints and order must match; no bearer
URLs are recovered from storage and no old emails are automatically rescanned.
Changed/missing completed files cause a protective failure, not an overwrite.
Cross-computer journal migration and retention/backup automation are future work.

## Sensitivity labels are unchanged — not Public

Ordinary XLSX bytes can be inspected without Excel, so collection does not trigger
Excel's interactive label picker. It does **not** apply Public, grant permission to
leave a file unlabeled, or change classification/encryption. The UI/manifest say labels
are unchanged. Protected/unsupported files are rejected, not decrypted or downgraded.
[Office label behavior](https://learn.microsoft.com/en-us/purview/sensitivity-labels-office-apps).

If approved automatic Public labeling is required, obtain each tenant's published
label mapping and approved authenticated mechanism. Do not fabricate label metadata
or assume a display name maps to a universal ID. Preserve the original and verify
a separately labeled copy. That capability is not implemented in this slice.
[Excel label API](https://learn.microsoft.com/en-us/office/vba/api/excel.workbook.sensitivitylabel).

## Verification and remaining acceptance work

Synthetic coverage spans parsing, newest-N selection, hostile links/workbooks, duplicates,
recovery, frozen reviews, cancellation and coordinated shutdown. Offline helper tests
reject an invalid action before COM access, including source/pythonw private pipes.
Full-suite and bundle results must be checked in PROJECT_STATE; synthetic passes
do not establish live client behavior.

Before calling M3 accepted:

1. Verify the supplied forwarded samples through the implemented download/inspection
   path where links remain usable; retain only sanitized outcome evidence in Git.
2. Obtain an original direct email and verify it live; direct fixtures alone cannot
   establish real-world coverage. Verify forwarding in both organisations.
3. Obtain and embed an approved Microsoft public-client app ID, consent `Mail.Read`,
   then verify browser/MFA sign-in, Graph pagination and sign-out behavior in both
   organisations. Also confirm classic Outlook protection and enterprise proxies.
4. Confirm preserving labels is acceptable; Public assignment requires separate
   approval/configuration and implementation if mandatory.
5. Pass full regression and packaged smoke; review locked dependency notices,
   signing/installation gates, same-user recovery and errors on clean targets.
6. Obtain representative schemas before farm/date reconciliation, calculations,
   combined reports or analysis.
