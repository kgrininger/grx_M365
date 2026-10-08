# grx_m365 – Collaboration Architecture Summary

## 1. Why this document exists

This is a technical comparison input for discussion with the `frappe_microsoft365` maintainers. No migration decision has been made, and no repository has been selected as the eventual common foundation. We would first like to compare the authentication, account, and resource models and avoid maintaining duplicate Microsoft Graph stacks where practical.

## 2. Current grx_m365 model

- **`M365 Settings`** holds one site-wide tenant ID, app registration credentials, redirect URI, feature flags, and Calendar sync-window settings.
- **`M365 Account`** represents a delegated Microsoft connection and remains linked to a Frappe `User`. It stores the Microsoft email/UPN, tokens, granted scopes, and token expiry.
- **`M365 Calendar Account`** is a separate DocType linked to an `M365 Account`. It stores a calendar ID, target Frappe user, usage label, and pull-sync state.
- **`M365 Bookings Business`** is a separate Bookings resource linked to an `M365 Account`, with a business identifier and raw Graph payload.
- Microsoft Object ID and per-account tenant identity are not fully modeled. Tenant and app registration are currently global in Settings.

```text
M365 Settings (site-wide tenant + app registration)
       │
       ├── delegated OAuth ──> M365 Account ──> Frappe User
       │                           │
       │                           └── M365 Calendar Account ──> Frappe Event links
       │
       └── client credentials ──> Bookings API ──> M365 Bookings Business
```

## 3. Authentication model

### Delegated OAuth

`grx_m365` implements user-authorized OAuth. Access and refresh tokens are stored on `M365 Account`; Calendar background jobs can refresh a stored delegated token when needed. Those jobs do not need an interactive Frappe session, but they depend on prior Microsoft user consent, a usable refresh token, and the configured app credentials.

### App-only / client credentials

An app-only path exists today using the tenant and client credentials in `M365 Settings`. It is used by Bookings availability and appointment runtime paths and does not require an interactive Microsoft user session.

These delegated and app-only paths are separate implementations. They are not yet unified behind a generic Graph/auth abstraction; Calendar requests use their own delegated HTTP path, while Bookings has both delegated and app-only calls.

## 4. Resource separation – important design direction

A Frappe User, a Microsoft User, a Microsoft account/authentication context, and a Microsoft 365 resource do not need to be the same object. Resources may include personal, shared, room/resource calendars, Bookings Businesses, and future SharePoint Sites or Drives.

`grx_m365` already stores Calendars and Bookings Businesses as separate resource DocTypes. However, `Personal / Shared / Team / Resource` are currently mostly metadata/model concepts. Calendar pulls use delegated `/me` endpoints; real shared/resource Graph behavior is not fully implemented or tenant-tested. We do not want to overstate shared-calendar support.

## 5. Microsoft Bookings

The current connector includes Bookings Business import, service and staff reads, custom-question reads, booking-requirement generation, availability lookup, and appointment create/cancel paths. Delegated and app-only variants exist where needed; there is no local appointment synchronization model.

There is already a downstream integration contract with `grx_communication`, which calls Bookings functions for service discovery and runtime availability/booking. Bookings seems well suited to an optional module on a shared Microsoft Graph foundation rather than being part of a calendar-specific core.

## 6. Frappe-first requirement

The shared foundation should remain installable on plain Frappe without requiring ERPNext. ERPNext compatibility is welcome, but should be optional. `grx_m365` has no hard ERPNext dependency and currently uses Frappe Core concepts such as `Event` and `User`.

## 7. What looks stronger in frappe_microsoft365

Based on the maintainer description, `frappe_microsoft365` appears to have the stronger existing base around two-way Outlook ↔ Frappe Event sync, delta synchronization, recurrence, Teams meetings, recordings/transcripts, setup diagnostics, and broader automated tests/CI. We would like to understand those capabilities and their current boundaries rather than infer implementation details here.

## 8. What grx_m365 may contribute

Potentially useful input from `grx_m365` includes:

- Account/auth context separated from Calendar resource records.
- App-only/client-credentials requirements and unattended service use cases.
- Bookings integration and a downstream `grx_communication` contract.
- Requirements for shared, room, and resource calendars, while recognizing these are not fully implemented today.
- A plain-Frappe/no-hard-ERPNext constraint.

These are collaboration inputs, not a claim that `grx_m365` should become the common foundation.

## 9. Main architecture topics to compare

1. Tenant model and Microsoft identity model.
2. Relationship between Frappe User and Microsoft Account.
3. Separation of account/auth context from Calendar and other resources.
4. Delegated OAuth, app-only credentials, token storage, and refresh.
5. Background jobs that operate without interactive sessions.
6. Graph client abstraction, permissions, and consent.
7. Shared, room, and resource calendar behavior.
8. Bookings as an optional module.
9. Plain Frappe support without an ERPNext requirement.

## 10. Questions for frappe_microsoft365 maintainers

1. Is installation on plain Frappe without ERPNext supported and covered by CI?
2. How are Tenant, Microsoft Account, Frappe User, and Calendar represented today?
3. Is the Calendar currently tied to the signed-in/default Microsoft user?
4. How do you see separating an authentication account from Calendar resources?
5. Are app-only/client-credentials flows planned or supported?
6. Can delegated and app-only authentication coexist for different modules/resources?
7. How do background jobs obtain and refresh authentication without an interactive session?
8. How are shared, room, and resource calendars intended to work?
9. Would Bookings fit as an optional module on the shared Graph layer?
10. Is the auth/Graph layer intended to support later modules such as SharePoint?
11. Which DocTypes and Python APIs are considered stable extension points?

## 11. Preservation requirements

If `grx_m365` functionality is later moved onto `frappe_microsoft365`, these items must be explicitly preserved, replaced, or consciously retired:

- App-only Bookings runtime and delegated refresh behavior.
- Calendar Account separation, Calendar IDs, and target-user mapping.
- Bookings Business identifiers and existing `grx_communication` integration contracts.
- Plain-Frappe installability without a hard ERPNext dependency.
- Existing Event and Event Link mapping data if a migration takes place.

**No existing capability should disappear silently.**

## 12. Suggested next step

Compare the authentication, account, and resource models; agree on a common target model; then decide what belongs in the core versus optional modules. Only after that should code migration or upstream contributions be discussed.
