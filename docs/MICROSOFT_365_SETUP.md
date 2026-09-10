# Microsoft 365 one-time deployment setup

This is for the application owner or Microsoft Entra administrator, not ordinary
Workbench users. Once the approved application ID is embedded in the installer,
users only press **Sign in with Microsoft 365** and complete their normal browser/MFA
flow. They never enter configuration, an email password, a client secret or a token.

## Registration request for IT

Create or approve a Microsoft Entra **public client / mobile and desktop application**:

1. Name it clearly, for example `SmaxTec Workbench`.
2. Choose the supported organisational account scope. If AHV and Elanco are separate
   tenants and one centrally owned build must serve both, use an approved multitenant
   registration and complete consent in each tenant. Otherwise issue a tenant-specific
   build/registration. Personal Microsoft accounts are not required.
3. Add the Mobile and desktop application redirect URI `http://localhost`.
4. Add Microsoft Graph **delegated** permission `Mail.Read`. Do not add application
   mailbox permissions, write/send permissions, or a client secret.
5. Complete the tenant's publisher, user/admin-consent and security review. Some
   organisations block user consent for `Mail.Read`, in which case an administrator
   must grant it.
6. Give the development/release owner the **Application (client) ID**. It is a UUID
   and not a secret. Never send a client secret, access token or mailbox data.

Microsoft references:

- [Register an application](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app)
- [Desktop redirect URIs](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url)
- [Delegated Mail.Read permission](https://learn.microsoft.com/en-us/graph/permissions-reference#mailread)
- [Application consent policies](https://learn.microsoft.com/en-gb/entra/identity/enterprise-apps/manage-app-consent-policies)

## Development trial and production handoff

For an explicitly approved source-mode trial, a developer can set
`SMAXTEC_MICROSOFT_CLIENT_ID` to that application ID before starting Workbench. Do
not instruct an end user to do this. Before producing the distributable installer,
the release owner places the approved ID in `EMBEDDED_MICROSOFT_CLIENT_ID` in
`src/smaxtec/adapters/mail/graph.py`, rebuilds from the locked dependencies, and
repeats all package/release checks. The desktop application contains no secret.

## Acceptance check

On a standard target computer:

1. Press **Sign in with Microsoft 365** and verify the browser shows the intended
   application name/publisher, intended work account and only the reviewed permission.
2. Complete normal MFA. Confirm Workbench lists the signed-in user's Inbox without
   requiring any Outlook desktop application.
3. Scan a bounded lookback containing a direct export, an inline forward and an inline
   forward of a forward. Confirm the newest-N preview is correct and mail remains unread.
4. Download only a reviewed synthetic/test export selection; check duplicate/problem
   behavior and B3-derived filenames without recording links or mailbox contents.
5. Press **Disconnect**, then confirm another scan requires reconnecting. Close the app
   during sign-in and during a scan to verify bounded cancellation and cleanup.
6. Repeat for each supported tenant and its enterprise proxy/Safe Links policies.

Do not claim production acceptance from source-mode or synthetic tests. Code signing,
installer, clean-machine, consent, proxy and target-user checks remain separate gates.
