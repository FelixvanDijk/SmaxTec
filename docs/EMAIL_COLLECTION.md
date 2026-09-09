# M3: Email collection design and prerequisites

Status: design prepared on 2026-09-09; not implemented. Runtime remains 0.3.0.
The user has authorized M3. Resolve the connection decision and inspect original
and forwarded email samples before choosing an adapter or inventing download URLs.

## Required outcome

After checking that exports have arrived, the user opens a new collection section
below the website request controls. They connect/select their own mailbox, choose
how many recent export emails to collect, review the selection and download them
into one clearly identified folder. Excel need not open to identify or rename files.
Mailbox connection is independent of the smaXtec account/session.

Initial users receive corporate Outlook mail at AHV and Elanco. Exports may be
received directly from `noreply@smaxtec.com` or forwarded by another person. There
is a download link, not a workbook attachment. The supplied screenshot says the
link is available for **24 hours**. Request order is not arrival order.

Read-only inspection of the supplied local workbook found two worksheets with
the same numeric-string B3 value, no custom properties, and no macro/external-link
parts. The file was not modified or opened in Excel. This is one structural sample,
not a guarantee about every export, spreadsheet identity or corporate label policy.
Do not commit that workbook, email bodies, screenshot or full download links.

## Decision to confirm: mailbox connection

| Route | User experience | Prerequisites and limitations |
| --- | --- | --- |
| Microsoft Graph delegated OAuth — recommended cross-user route | Connect Microsoft account, normal Microsoft sign-in/MFA, then select an authorized mailbox/folder | Developer/IT-owned app registration and tenant consent/access policies; does not depend on Outlook desktop edition |
| Classic Outlook adapter — possible initial route if confirmed | Use an already configured Outlook profile and explicitly choose its mailbox | Installed/configured classic Outlook for Windows and permitted programmatic access; does not cover new-Outlook-only users |
| Import saved email files — possible fallback, not an inbox connector | User selects/saves the desired messages and imports them | No automatic newest-N inbox scan; confirm saved formats and forwarding examples before implementation |

Microsoft marks Outlook Object Model/MAPI unsupported in new Outlook. Bundling
`pywin32` cannot add that capability. New Outlook was running on the development
computer during inspection; classic COM registration also exists, which does not
establish that a usable classic profile is configured.
[Outlook feature comparison](https://support.microsoft.com/en-us/outlook/getstarted/feature-comparison-between-new-outlook-and-classic-outlook).

For Graph, provision a public-client application for organizational accounts; do
not ship a client secret or capture the mailbox password. Start with delegated
`Mail.Read`, not Mail.Send/Mail.ReadWrite or organization-wide application access.
Message bodies are needed for links, so Mail.ReadBasic is insufficient. Shared
mailboxes require existing user access and the appropriate delegated permission;
add that capability only when required. Microsoft recommends a registered native
redirect for interactive desktop authentication. Keep tokens in memory initially.
[MSAL public clients](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/client-applications),
[interactive authentication](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens),
[Graph permissions](https://learn.microsoft.com/en-us/graph/permissions-reference),
[shared mail](https://learn.microsoft.com/en-us/graph/outlook-share-messages-folders).

Do not promise end-user consent will work: tenant policy, app assignment and
Conditional Access can require IT involvement. Microsoft's managed recommended
consent policy excludes ordinary apps' Mail.Read/Mail.Read.Shared user consent.
The development team/IT owns setup once; ordinary users must not create their own
registrations, enter client IDs, install packages or edit configuration files.
Confirm Microsoft 365/Exchange Online hosting rather than inferring it from the
email domains. Confirm whether Windows broker/device-compliance support is required.
[Consent policies](https://learn.microsoft.com/en-gb/entra/identity/enterprise-apps/manage-app-consent-policies).

For classic Outlook, never silently use the default account. Enumerate permitted
accounts/stores, obtain explicit selection, and use that store's Inbox. The supplied
example's Namespace.GetDefaultFolder selects the default store. HTMLBody/Body and
address properties can trigger Outlook's programmatic-access guard. Never disable
it. Isolate COM work in a bounded helper process if prompts can block cancellation;
do not call Quit on the user's Outlook application.
[Store Inbox](https://learn.microsoft.com/en-us/office/vba/api/outlook.store.getdefaultfolder),
[protected properties](https://learn.microsoft.com/en-us/office/vba/outlook/how-to/security/protected-properties-and-methods).

## GUI and selection contract

Proposed controls (labels can be refined during visual testing):

1. **3. Collect emailed exports** — separate account status and Connect/Disconnect.
2. Mailbox/folder selection (Inbox by default), **Latest [10] matching emails**,
   visible received-date/lookback controls and **Save to [folder] / Browse**.
3. **Find export emails** — user-triggered; no polling or automatic downloads.
4. A scrollable preview: received time, sender, subject, direct/forwarded status,
   previous collection status and any ambiguity/expiry warnings.
5. **Download these N emails** — freezes the reviewed message IDs; progress,
   cancellation, per-item errors and an **Open collection folder** action.

"Latest 10" means ten qualifying messages, newest by the chosen folder's received
time, not the ten newest arbitrary inbox messages. For forwarded mail this is the
outer message's received time, not the original export creation time. Pagination
must be ordered and bounded. Show when a scan/lookback limit was reached or fewer
than N matches were found. Do not silently scan an entire mailbox indefinitely.
[Graph paging/order](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0).

Freeze the candidate selection for review and download: a new email arriving later
must not change it. Exact duplicate links/messages are reported, not silently
replaced with older messages. If one email contains multiple different export links,
require explicit disambiguation; N emails does not automatically mean N cows/files.
Failures do not "top up" the batch with older emails. Requesting new website exports
is never a side effect of collection, retries or expired links.

Inbox access is read-only: do not mark read, move, delete or modify messages.
Do not render HTML or load email images/scripts. Recognize direct sender SMTP
exactly; forwarded mail needs both recognizable export content and a verified
download-link pattern. Quoted From text/display names are not authentication.
Attached-message forwards (`.eml`/`.msg`) need explicit support/tests if present.

## Download trust boundary

Inspect the actual href and redirect chain from authorized original/forwarded
samples before implementing the production allowlist. The screenshot alone cannot
establish the host, signature parameters, Safe Links wrapping or landing-page flow.
All development/CI fixtures must use synthetic messages and links.

- Allow only confirmed HTTPS origins/path patterns. Validate every redirect,
  with bounded redirect count, size, duration and cancellation. Reject URL
  credentials, insecure protocols, private/local/link-local destinations,
  unexpected ports and unrecognized hosts. Do not allow all AWS/Azure domains.
- Never include website/Microsoft tokens or cookies in file-host requests. Use an
  isolated downloader; direct HTTP versus a browser-mediated download depends on
  the verified flow and corporate protection behavior.
- Preserve Safe Links checks. Its embedded destination may aid classification,
  but do not fetch that destination directly to skip a warning or block. Do not
  click through security warnings or disable TLS/proxy protections.
- Handle expired/access-denied links, authentication challenges, interrupted
  downloads and HTML instead of XLSX as explicit failures. A generic 403 alone
  does not prove expiration. No unbounded retries.
- Treat full URLs as bearer secrets: never log, persist in manifests, display in
  diagnostics or include in exception text. Store only opaque source IDs and
  irreversible fingerprints as needed for deduplication.

Microsoft documents Safe Links as URL rewriting plus time-of-click checks.
[Safe Links](https://learn.microsoft.com/en-us/defender-office-365/safe-links-about).

## Workbook validation and cow identity

Validate the file itself, not merely its name or MIME type. Bound compressed size,
ZIP member count/uncompressed sizes and XML parsing; reject archive traversal,
macro-capable/unexpected formats and suspicious structures. Do not extract ZIP
members into arbitrary paths or execute formulas, macros or external links.
If using openpyxl, include its recommended XML hardening; do not rewrite files just
to rename them. [openpyxl security notes](https://openpyxl.readthedocs.io/en/stable/).

Read B3 from the agreed data worksheet(s). Confirm worksheet selection using further
samples; detect conflicting B3 values rather than trusting the active sheet. A blank,
formula, error or ambiguous identifier is a visible validation failure.

For text identifiers, accept an anchored numeric value with an optional parenthesized
annotation: `203 (new girl)` becomes `203`; `00203` remains `00203`. Do not simply
remove every nondigit: `203/204` must not become `203204`. Specify and test numeric
cell handling separately. Keep the original B3 text as provenance outside Git.

B3 is an **animal name**, whereas website lookup uses **Animal number**. Their
equality must not be assumed universally. B3 alone cannot prove farm, export period
or which website batch produced a workbook. Newest-N collection remains independent;
record any requested batch as context, not a verified match. Farm/period reconciliation
requires confirmed workbook metadata and later acceptance tests.

## Destination, naming and durable state

Offer the OS-resolved Documents folder via Qt standard paths, not a username,
hardcoded drive or assumed OneDrive directory. Let the user change it with Browse.
Proposed default: `Documents/SmaxTec Workbench/Collections/`.
Create a unique timestamp + random-ID folder for every reviewed collection.

Within it, retain validated original bytes under names such as `cow-203.xlsx` and
`cow-203__02.xlsx`. Multiple periods for one cow are legitimate. Never overwrite a
previous file, trust a server filename as a path, or modify unrelated Downloads files.
Stage incomplete data separately and publish completed files atomically with
collision-safe reservation. Failed identification can be quarantined and surfaced
for review; it must not silently enter future analysis as validated cow data.

Add a small local SQLite collection journal in the OS-resolved per-user application
data directory, plus a useful manifest in the collection folder. Record batch/item
IDs, selected mailbox/folder reference, source message ID/received time, app version,
status/error code, original/saved filename, cow identifier and SHA-256. Do not store
email bodies, credentials, session cookies or bearer links.

Persist the reviewed selection before download work. Record per-item progress so
cancellation, a crash or restart does not lose completed files. Retry only explicitly
selected failed items, reacquiring links from authorized messages rather than storing
bearer URLs. Reconcile an interrupted publish by verifying the file/hash; never
silently overwrite. Present previously collected items as such, with an explicit
reuse/retry choice; do not silently skip them and substitute older messages.

## Sensitivity labels: separate, policy-aware capability

Reading ordinary XLSX bytes without Excel avoids triggering Excel's open/save label
UI. It does **not** classify the file as Public or establish permission to leave it
unlabeled. Mandatory labeling is documented as an Office open/save behavior;
confirm the organisation's actual policy for this automated collection workflow.
[Office labeling behavior](https://learn.microsoft.com/en-us/purview/sensitivity-labels-office-apps).

Preserve original metadata and encryption. Do not downgrade an existing label,
fabricate Public metadata or bypass restrictions on protected files. If automatic
Public labeling is required for these exports, obtain each organisation's published
label mapping and approval and choose a supported authenticated mechanism. Excel's
SensitivityLabel API requires compatible Excel; Microsoft Information Protection
SDK introduces additional identity/runtime/deployment requirements. The displayed
name alone is not a universal label ID. Save and verify a labeled copy while retaining
the original; report "label unchanged" unless labeling actually succeeded.
[Excel label API](https://learn.microsoft.com/en-us/office/vba/api/excel.workbook.sensitivitylabel),
[SetLabel](https://learn.microsoft.com/en-us/office/vba/api/office.sensitivitylabel.setlabel),
[MIP prerequisites](https://learn.microsoft.com/en-us/information-protection/develop/setup-configure-mip).

## Implementation slices and acceptance tests

1. Resolve mailbox route/tenant prerequisites; inspect sanitized original and
   forwarded message structures, href/redirect behavior, worksheet identity and policy.
2. Add typed mailbox/message/collection contracts and read-only candidate discovery
   through the selected adapter. Test mixed inboxes, pagination, multiple accounts,
   forwarding, ambiguity, latest-N boundaries and frozen selections.
3. Add download validation, B3 extraction, collision-safe files and durable collection
   state. Test expired/blocked/redirected links, hostile HTML/XML/ZIP, invalid IDs,
   repeated cows/different periods, cancellation, resume and filesystem errors.
4. Add the GUI card, review table, progress/results and folder actions with blocking
   work off the GUI thread. Verify account disconnect and application shutdown.
5. Verify label handling only against approved policies/methods, preserving originals.
6. Run full regressions and packaged Windows smoke tests. Perform a narrowly scoped,
   user-approved live collection against both organisations and direct/forwarded mail.
   Confirm no mailbox changes and no credentials/links in repository or diagnostics.

### Inputs still needed

- Must the initial release support new Outlook/browser-only users, or is classic
  Outlook installed/configured for everyone?
- Who can own an approved Microsoft app registration and arrange AHV/Elanco consent
  if Graph is selected? Confirm mailbox hosting and any shared-mailbox need.
- One original and one representative forwarded export email as `.eml`/`.msg` or
  their local paths. Keep full URLs private; a screenshot is insufficient for hrefs.
- Whether Public must be applied by this workflow itself; if so, tenant-specific
  approved label details and a supported authenticated labeling method.
