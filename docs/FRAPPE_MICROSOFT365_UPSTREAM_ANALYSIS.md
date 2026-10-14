# frappe_microsoft365 Upstream Analysis

**Purpose:** read-only architecture and capability-fit comparison. No implementation, migration, dependency change, code transfer, or contribution has been performed.

**Evidence baseline:** `grx_m365` branch `feature/bookings-application-token`, commit `ebcd10c787dec39ffccc06577e73680e8eb887eb`; `frappe_microsoft365` branch `main`, commit `ec303f6cc84e6a0a9926e388266edf5c5b68cdbb`. The existing GRX audits were written 2026-10-08. This document checks their claims against the code at these checked-out commits. “Implemented” means code exists; “tested” means a relevant test exercises it, not that production operation has been established.

## 1. Executive summary

`frappe_microsoft365` is the stronger current foundation for a common Microsoft integration where its existing code applies: it has a shared delegated Graph transport, two-way Frappe Event sync, delta cursors, recurrence mapping, owner-scoped `Microsoft Calendar` records, a tested queue/locking strategy, operational diagnostics, and CI for Frappe 15 and 16. It also has Teams meeting and transcript/recording capabilities. These are materially more complete than the matching GRX calendar implementation.

It is not a drop-in replacement for `grx_m365`. Its calendar record combines a Frappe User, a delegated Microsoft identity, one selected/default calendar, and sync state. Its Graph client resolves delegated tokens from that calendar record. The checked-in Graph client does not provide a Graph client-credentials path, and the app has no Bookings module. Application OAuth exists for the separate Outlook mail configuration, which does not establish app-only Graph support.

`grx_m365` contributes requirements and a working-but-lightly-tested Bookings implementation: separate Calendar Account and Bookings Business records, target-user mapping, app-only Graph calls for Bookings availability and appointment mutations, delegated Bookings reads/mutations, and a direct `grx_communication` Python contract. Its Personal/Shared/Team/Resource labels do not prove working shared/resource calendar access; calendar calls still use `/me` delegated endpoints. The GRX integration and its security/test gaps need to be treated as preservation and design inputs, not as evidence of production readiness.

Likely direction, subject to maintainer agreement: keep the upstream app as the common core, first agree on tenant/auth/resource abstractions, then add Bookings as an optional module using a shared Graph transport with explicit delegated and application auth contexts. Keep GRX caller behavior in a compatibility adapter or a separate GRX integration app. Shared/resource calendars require a core resource/auth model decision before migration. No capability should be retired based only on absent tests or absent upstream code.

## 2. Side-by-side architecture comparison

| Area | `frappe_microsoft365` | `grx_m365` |
|---|---|---|
| Repository baseline | `main`, `ec303f6`; clean checkout | `feature/bookings-application-token`, `ebcd10c`; one commit ahead of origin at inspection |
| Packaging / Frappe support | `pyproject.toml`: Python >=3.10; declared `msal` and `requests`; Bench Frappe range >=15,<17; CI installs, migrates, and tests Frappe 15 and 16 | `pyproject.toml`: Python >=3.10; no declared runtime dependency; no explicit Frappe support range; CI initializes default Bench/Frappe without a version matrix. Runtime imports `requests` without declaring it. No `required_apps` / ERPNext dependency found |
| Core DocTypes | `Microsoft Settings`, `Microsoft Calendar`; setup adds custom fields to core `Event`. `Microsoft Calendar` carries OAuth tokens, Frappe user, Microsoft account email, one calendar ID, and sync state | `M365 Settings`, `M365 Account`, `M365 Calendar Account`, `M365 Event Link`, `M365 Calendar Sync Log`, `M365 Bookings Business` |
| Graph / API surface | `microsoft_graph.py` shared delegated client; calendar, meeting, RSVP and artifacts operations; whitelisted calendar actions and diagnostics | separate `api/auth.py`, `api/graph_client.py`, `api/calendar_pull.py`, `api/bookings.py`; Bookings functions are whitelisted and also imported directly by another app |
| Scheduled work | 15-minute cron calls calendar sync and meeting artifact fetch. Calendar changes also enqueue after commit from Event hooks | hourly scheduler enqueues each enabled pull calendar. No Bookings scheduler |
| Tests / CI | Ten test modules; Graph paging/delta/throttling/token caching, sync semantics, recurrence, ownership, background and diagnostics are exercised. CI runs Frappe 15/16 matrix plus Semgrep | Three test files discovered; two DocType test classes are empty; `test_calendar_pull.py` tests an internal Event save flag, not end-to-end Graph behavior. CI runs only a default Frappe Bench target, without an explicit version matrix |
| Auth | Per-`Microsoft Calendar` delegated auth-code flow via MSAL; encrypted Frappe Password token fields; app-only flow supported for Outlook mail through Frappe Email Account/Connected App config, not through the Graph client | Delegated auth-code flow with global tenant/app settings; Password token fields on `M365 Account`; Graph app-only client credentials token cached for Bookings calls |
| Calendar | Pull and push, delta sync, event hooks, recurrence mapping, delete handling, per-calendar lock | Pull only, rolling `calendarView` window, link/hash dedupe, cancellation/removal marking; no delta, recurrence treatment, or lock |
| Teams | Event-associated Teams meeting creation, standalone meetings, meeting artifact lookup, transcript and recording retrieval (feature/permission dependent) | No Teams capability identified |
| Bookings | No Bookings DocType, API, or module identified | Business import, service/custom question/staff reads, requirement generation, availability, appointment create/cancel; delegated and app-only paths for relevant calls |
| SharePoint / OneDrive | No capability identified in checked app code | No capability identified |
| Permission/security model | `Microsoft Calendar` has row-level query and object permission hooks; owner checks on calendar actions; OAuth state generated per calendar, expiring and consumed at callback; guest OAuth callback only | DocType roles exist but API object authorization is uneven. OAuth state is the Frappe username and callback accepts guest; no visible state/session/nonce check. Calendar sync blocks Guest but does not show a per-record owner check. Some worker writes use `ignore_permissions=True` |

## 3. Implemented vs tested vs prepared

| Capability | `frappe_microsoft365` | `grx_m365` |
|---|---|---|
| Delegated OAuth / token refresh | Implemented via MSAL; state expiry/lookup/owner check present; covered by relevant tests | Implemented with raw token requests; state is username; no relevant auth tests |
| Graph request layer | Implemented and used for delegated Graph calls; paging/delta/429/401/cache behavior tested | Split delegated and app-only helpers; Bookings has another delegated wrapper; no retry/throttle abstraction; no relevant tests |
| Two-way calendar sync | Implemented and extensively unit/integration tested | Not present; pull-only implementation |
| App-only Graph | Not present as a common Graph transport. Mail app-only configuration is a different protocol path | Implemented for Bookings availability/create/cancel, untested; absent for calendar pull |
| Bookings | Absent | Implemented surface, lightly supported by tests; two DocType tests are empty, and current tests do not exercise Graph Bookings paths |
| Resource calendars | One calendar record per Microsoft connection; no shared/resource selector or independent auth/resource model | Separate calendar record and usage metadata; actual non-`/me` shared/resource behavior absent/unproven |
| Setup doctor | Implemented with many configuration/permission/error checks and test coverage | No setup doctor identified; error fields/settings only |

## 4. Foundation comparison

Classification vocabulary follows the request. “Stronger” describes the specific topic, not an overall winner.

| Topic | Classification | Evidence and architectural consequence |
|---|---|---|
| Tenant model | `different approaches` | Both use a site-wide `Microsoft Settings` single with a tenant ID. Neither models multiple tenants as first-class entities or scopes every external resource to a tenant record. A shared foundation should add tenant identity before multi-tenant/resource migration. |
| Microsoft identity/account model | `different approaches` | GRX separates delegated `M365 Account` from `M365 Calendar Account`, but identifies the Microsoft principal mainly by email and lacks per-account tenant/object IDs. Upstream `Microsoft Calendar` combines credentials, Microsoft email, user and one calendar. GRX separation is a useful requirement; upstream has more complete token lifecycle behavior. |
| Frappe User relationship | `frappe_microsoft365 stronger` | Upstream enforces owner scoping through query and object permission hooks and checks ownership in endpoints. GRX records `target_user` for imported events but does not show comparable calendar-account row-level hooks or endpoint ownership checks. |
| Calendar/resource model | `grx_M365 stronger` | GRX has a distinct Calendar Account with ID, target user, and usage metadata. Upstream calendar record is also a resource ID, but is tightly coupled to a single delegated connection and user. Neither has demonstrated shared/resource calendar runtime behavior. |
| Delegated OAuth | `frappe_microsoft365 stronger` | Upstream uses MSAL, per-calendar expiring stored state, owner checks, and token caching/refresh tests. GRX has raw OAuth and unsafe state association by username, with no auth test evidence. |
| App-only / client credentials | `grx_M365 stronger` | GRX has a Graph `.default` token provider and request path used for Bookings. Upstream has application OAuth configuration for mail, but no app-only Graph client found. GRX implementation needs endpoint-level authorization and tests before reuse. |
| Token storage / refresh | `frappe_microsoft365 stronger` | Both store delegated credentials in Frappe Password fields. Upstream MSAL lifecycle, request-local caching, 401 invalidation and refresh are tested. GRX refresh is implemented but has no relevant tests and less consistent error-state handling. Neither currently offers one reusable provider for delegated and app-only Graph. |
| Graph client abstraction | `frappe_microsoft365 stronger` | Upstream consolidates delegated Graph API transport and behavior. It still binds token resolution to `Microsoft Calendar`. GRX has separate transports by module and auth mode. A common abstraction should pass explicit auth/resource context rather than assume a calendar is the identity. |
| Pagination / retry / throttling / 429 | `frappe_microsoft365 stronger` | Upstream has next/delta paging guards, short `Retry-After` handling, 401 refresh retry, and tests. GRX follows next links in Calendar/Bookings but has no visible page cap, retry, or 429 handling. |
| Delta sync | `frappe_microsoft365 stronger` | Upstream persists delta link/window and restarts after invalidation. GRX rereads a rolling calendar window; `sync_interval_minutes` is stored but scheduler is hourly. |
| Recurrence | `frappe_microsoft365 stronger` | Upstream maps Frappe recurrence to Graph and handles pulled occurrences with tests. GRX does not model or test series/exception semantics. |
| Conflict/delete handling | `frappe_microsoft365 stronger` | Upstream supports both directions, avoids echo loops, handles removals and protects event mappings with sync logic/tests. GRX is pull-only with cancel/removal markers and hash dedupe, without conflict policy. |
| Background jobs | `frappe_microsoft365 stronger` | Upstream queues slow work, has dead-queue diagnostics, per-calendar locks, and after-commit Event scheduling. GRX has hourly queue dispatch and logs but no lock/dedupe/retry. Both rely on stored delegated refresh for unattended delegated calls. |
| Setup diagnostics / doctor | `frappe_microsoft365 stronger` | Upstream doctor checks settings, scopes, Connected App/mail config, errors and queue health, with test coverage. GRX has settings and last-error fields, no equivalent diagnostic subsystem identified. |
| Permissions / consent | `frappe_microsoft365 stronger` | Upstream derives delegated scopes from selected capabilities and diagnoses configuration. GRX scope flags are simpler and app-only permission consent is not diagnosed. Both still require careful admin-consent setup; Bookings app-only creates a new high-impact authorization surface. |
| Plain Frappe without ERPNext | `both incomplete` | Neither declares ERPNext as a required app or showed direct ERPNext imports in the inspected paths. Upstream documents Frappe/ERPNext and tests install against Frappe 15/16, while GRX has no Frappe version matrix. Plain-Frappe support should be made an explicit compatibility requirement and tested for the selected target. |

## 5. Capability gap matrix: preserve GRX requirements

Codes: **A** fully covered upstream; **B** partly covered; **C** missing and likely upstreamable; **D** optional module; **E** adapter/migration required; **F** GRX-specific/outside common app. These are proposed disposition categories, not approval to drop functionality.

| GRX capability | Upstream state | Disposition | Required path / caveat |
|---|---|---|---|
| Plain Frappe, no hard ERPNext dependency | No ERPNext requirement apparent; Frappe 15/16 install CI exists | B, C | Retain no-hard-ERPNext constraint and test clean Frappe install in target CI. |
| Delegated OAuth and background refresh | Upstream has stronger delegated flow and refresh | A, E | Map each GRX account to an upstream connection; existing tokens may need reconnect because storage/ownership differs. |
| App-only / client credentials for Graph | No common app-only Graph client | C, D, E | Upstream a generic app-only provider with permission/consent model; Bookings uses it optionally. Do not assume mail application flow covers Graph. |
| Bookings Business | Absent | C, D, E | Optional Bookings module and business identity mapping; retain business IDs and tenant/account binding. |
| Bookings service reads | Absent | C, D, E | Reimplement against common Graph transport; preserve response names or adapt callers. |
| Bookings staff reads | Absent | C, D, E | Same; include pagination and permissions. |
| Custom questions | Absent | C, D, E | Preserve question metadata and requirement generation semantics. |
| Booking requirement generation | Absent | C, D, E | Domain helper likely belongs in optional Bookings module, independent of voice-bot concepts. |
| Availability | Absent | C, D, E | Preserve availability request/response semantics and timezone handling; likely app-only where service runtime requires no user connection. |
| Appointment create/cancel | Absent | C, D, E | Support auth context explicitly; consider idempotency and authorization. |
| Delegated + app-only Bookings paths | Absent for Graph | C, D, E | Both can coexist if auth mode is an explicit per-operation/resource choice and app-only operations are server-authorized. |
| Separate Calendar Account / multiple Calendar IDs | Upstream has one calendar ID per Microsoft Calendar connection | B, E | Either refactor upstream resource model or retain a GRX resource adapter; avoid duplicating OAuth per calendar. |
| Target Frappe User mapping | Upstream connection owner is Frappe User; imported event ownership follows connection | B, E | Map existing target owners and establish explicit service-account/resource ownership semantics. |
| Personal / Shared / Team / Resource metadata | Upstream absent; GRX stores labels, but Graph behavior is not implemented | C, E | Preserve classification as metadata only until paths/permission rules are specified. Do not claim current shared access. |
| Background delegated refresh | Upstream scheduled sync refreshes delegated tokens | A, E | Verify worker use cases and token reconnect behavior before retiring GRX jobs. |
| Event Link, hash and sync metadata | Upstream uses Event custom fields and Graph IDs, delta cursor; schema differs | B, E | Translate or retain mappings. Never re-create Graph events blindly from missing IDs. |
| `grx_communication` integration contracts | Absent; no callers currently target upstream | E, F | Compatibility adapter or coordinated caller migration; provider-specific voice-bot mapping remains GRX-specific. |
| Optional `grx_fieldservice` context | No equivalent upstream | D, F | Keep as optional adapter outside common core; preserve current imported-event context behavior only if still required. |
| Settings/debug/window fields | Different settings model; some GRX fields unused | B, E | Migrate active configuration selectively; archive obsolete fields. |
| SharePoint / OneDrive | Absent in both | C, D | Future optional module only after auth/resource abstraction supports sites and drives. |

## 6. Bookings fit analysis

### Current scope and reuse

The GRX Bookings module contains the following code paths: business list/upsert; business, service, custom-question, and staff reads; service requirement generation; availability via `getStaffAvailability`; appointment creation; and cancellation. Delegated reads and delegated appointment mutation use the linked `M365 Account`. App-only availability, appointment creation, and cancellation use the site-wide client credentials helper. There is no local appointment persistence, appointment sync, webhook, or Bookings background worker.

Conceptual reuse is substantial at the domain level: endpoint/payload knowledge, custom-question interpretation, requirement generation, the dual-auth requirement, timezone input, and the `grx_communication` result contract. Direct code reuse would be premature. GRX request functions own their token lookup, HTTP handling, pagination, and Frappe records, while upstream Graph calls take a `Microsoft Calendar` name and resolve delegated tokens from that record. A Bookings resource must not be made to impersonate a calendar simply to obtain a token.

### Where auth should come from

Bookings should request an explicit auth context from the common layer. For example, the operation may be delegated under an authorized Microsoft user, or application-authenticated using a configured tenant/application credential with Bookings application permissions. The business record should bind to a tenant and resource ID; the authorization layer should decide whether the current caller/job is allowed to use that context. Tokens and secrets must not be returned to the Bookings module or caller.

Delegated and application flows can coexist cleanly if auth mode is explicit, scopes/roles are distinct, and resource ownership is checked. Avoid implicit “try delegated, fallback app-only”: it changes consent and authority without the user/caller knowing. App-only availability and writes should be exposed only through server-side authorized operations; a public/guest booking workflow needs a narrowly scoped application service, input validation, abuse controls, and idempotency, not direct unauthenticated access to a generic Graph method.

### Packaging tradeoffs

| Option | Benefits | Costs / risks | Assessment |
|---|---|---|---|
| Bookings in core | One install and common auth/Graph path; easier diagnostics and integration testing | Adds domain-specific schema, scopes, UI and risk to every install; can burden calendar-only users | Not the preferred default unless maintainers want the app to cover all Microsoft 365 services |
| Optional module inside same app | Shared code and versioning; Bookings DocTypes/UI can be conditionally installed or feature-gated; simpler auth integration | Optional DocType migration and conditional hooks need careful design; module boundaries must stay real | Good if Frappe app conventions and maintainers support optional feature modules |
| Separate Frappe app depending on `frappe_microsoft365` | Keeps generic core small; clear Bookings lifecycle; independent release cadence | Requires stable public auth/Graph extension API and dependency/version coordination; avoid importing internals | Good alternative if the core app will not accept optional service modules |

Recommended starting point: agree on a stable common auth/Graph interface first, then decide whether Bookings is an optional module in the same repository or a separate app. In either case, keep voice-bot/provider-specific data and the `grx_communication` integration adapter outside common Bookings domain code.

## 7. Account and resource separation

### Current coupling

In upstream, `Microsoft Calendar` is named by `account_name` and contains `user`, Microsoft email, OAuth state, access/refresh tokens, authorization, calendar ID/name, and sync settings/cursors. One record therefore represents a Frappe user’s delegated Microsoft connection and one calendar. Calendar operations use `/me` endpoints; the record is both token selector and calendar selector. This is simple and matches personal calendars, but it cannot naturally express multiple resources under one identity, an app-only resource with no user, or a Bookings Business as a resource.

In GRX, `M365 Account` is the delegated identity/token record linked to a Frappe User. `M365 Calendar Account` separately identifies a calendar ID, target Frappe User, usage label, and pull state. `M365 Bookings Business` is another resource DocType. This is a better conceptual separation for resource ownership and multiple resources per auth identity. However, tenant and app credentials are still global; Microsoft identity is email-based; usage labels do not select Graph endpoints/auth; and calendar pulls remain under `/me`.

### Needed target model

Before supporting shared calendars, rooms/resources, multiple calendars, app-only resources, Bookings, and future SharePoint, maintainers should agree on separate concepts:

1. **Tenant / application registration**: tenant ID and credential reference; permissions/consent status.
2. **Auth connection/context**: delegated principal or application identity, token lifecycle and granted scopes/roles; may have an associated Frappe owner but not require one.
3. **Microsoft resource**: typed Calendar, Bookings Business, SharePoint Site/Drive, external resource ID, tenant, and selected access context.
4. **Frappe mapping**: which User/team/doctype owns imported content and who may read or operate on it.
5. **Sync state**: per-resource delta cursor, lock, error, and idempotency/mapping records.

This is a core refactor, not a safe extension of `Microsoft Calendar` by adding a `Shared` choice alone. Shared-calendar delegated behavior, room/resource access, and app-only calendar access must each be designed and tenant-tested. Neither repository currently demonstrates those paths. Future SharePoint is a further argument for an explicit resource/auth layer, not for treating every Graph object as a calendar.

## 8. Migration and data impact

No migration should be built until target records, ownership, tenant boundaries, and reconnect policy are agreed.

| GRX data | Likely treatment | Notes |
|---|---|---|
| `M365 Settings` | Transform selectively; archive source | Move tenant/client configuration only through an approved secret-handling plan. Preserve active calendar window/module flags; `sync_interval_minutes` is not honored by current hourly hook and `debug_enabled` is not shown as used. Do not copy secrets into logs/export files. |
| `M365 Account` | Map identity; likely reconnect | User/email/status/scope/expiry can be mapped as metadata. Token formats and record ownership differ. Prefer user reconnect unless a supported, secure token migration is established; never assume refresh tokens can be reused without validation. |
| `M365 Calendar Account` | Transform to resource mapping | Preserve calendar IDs, labels, target user, enabled/pull flags and sync timestamps. Current upstream has one calendar per identity record; this requires core multi-resource support or adapter storage. |
| `M365 Event Link` | Transform or retain as adapter mapping | Preserve Microsoft event ID, Frappe Event link, iCal UID/change key, webLink, hash and cancellation state. Map to upstream Event custom fields only after matching ownership and sync semantics. |
| `M365 Calendar Sync Log` | Archive or transform | Preserve audit history where required; do not treat old rolling-window counters as upstream delta history. Define retention before importing logs. |
| `M365 Bookings Business` | Transform into Bookings resource | Preserve business ID, owning tenant/account, enabled/publish state, timezone, raw metadata and any delegated auth account. Current upstream has no matching DocType. Resolve global uniqueness to tenant-scoped uniqueness. |
| Tokens / reconnect | Reconnect preferred; secure migration only if proven | Upstream uses its own MSAL flow and token fields. Test revocation, expiry, scopes and principal identity before deciding. Plan user-visible reconnect state. |
| Calendar IDs | Preserve as resource IDs | IDs can be retained as opaque Microsoft identifiers, but the destination must know the correct tenant and auth context. |
| Microsoft event IDs | Preserve | Needed to prevent duplicate outbound creation and map updates/deletes; validate against destination resource before activating sync. |
| Bookings business IDs | Preserve | Bind to tenant and business; IDs alone are not globally safe across tenant contexts. |
| Target-user mapping | Transform explicitly | Map `target_user` to upstream owner/authorization semantics or a separate resource owner field; do not silently assign all imported events to the connection creator. |

## 9. Caller and API impact

No current imports of `frappe_microsoft365` were found in `grx_communication` or `grx_fieldservice`. `grx_communication` imports `grx_m365.api.bookings` directly in `appointment_offerings.py` and `appointment_runtime.py`.

### GRX caller contract

| Function | Caller expectation |
|---|---|
| `list_services(bookings_business)` | `{"services": [...]}` with Graph service dictionaries; used to import offerings |
| `get_service(bookings_business, service_id)` | `{"service": {...}}` |
| `get_service_booking_requirements(bookings_business, service_id)` | Service metadata plus `custom_fields` entries containing question ID, label, type, source and required flag; may include staff member IDs |
| `list_staff_members(bookings_business)` | `{"staff_members": [...]}` |
| `get_staff_availability(bookings_business, staff_ids, start_date_time, end_date_time, timezone)` | `{"availability": ...}` consumed by slot extraction |
| `create_appointment[_application](bookings_business, service_id, start_date_time, end_date_time, customer_name/email/phone, staff_member_ids, timezone, notes, custom_answers)` | `{"appointment": {...}, "appointment_id": ...}`; runtime returns the resulting appointment ID |
| `cancel_appointment[_application](bookings_business, appointment_id, cancellation_message)` | Result passed through as operation result; delegated/app-only variants selected explicitly by endpoint |

These Python functions are also marked whitelisted. Their payload shapes are application contracts even though no versioned public API schema is present. `grx_fieldservice` has an optional dynamic call to `grx_fieldservice.api.event_context.resolve_event_context` from GRX calendar import; this is a GRX-specific integration seam, not an upstream contract.

### Compatibility strategies

1. **Temporary adapter (recommended during transition):** preserve `grx_m365.api.bookings` names and result dictionaries while delegating to the new Bookings provider. Keep caller-facing validation and error conventions stable. This is a migration bridge, not a permanent duplicate Graph stack.
2. **Provider interface:** define a small `BookingsProvider` contract in `grx_communication` or a GRX adapter package so other providers are not imported as a concrete GRX app. Do not put voice-bot payload shape in common Microsoft core.
3. **Coordinated caller migration:** update offering import, requirements mapping, availability and appointment runtime together; protect the response shapes with adapter/integration tests before removing old imports.
4. **Whitelisted aliases:** only if browser/API callers are identified. Preserve authentication, argument names, response schema and authorization; do not create aliases that expose generic app-only Graph calls.

## 10. Security and operational quality

| Concern | Upstream observation | GRX observation / migration implication |
|---|---|---|
| OAuth state | Random per-calendar state with 15-minute expiry, matched to a record and owner-checked; state cleared on successful callback. This is materially stronger. Confirm replay behavior remains tested as lifecycle evolves. | State equals Frappe username; callback is guest-accessible and does not visibly validate state against session/nonce/one-time storage. Do not carry this flow forward. |
| Token handling | Frappe Password fields; tokens are not returned/logged by Graph layer; request-local token cache; 401 invalidates and refreshes once. | Password fields and application token cache exist. Error paths can include raw response text; credential cache invalidation on settings change is unclear. |
| Object permissions | Calendar row query and object permission hooks; explicit owner check on actions; System Manager/Administrator override. | Doctype role permissions exist, but many API calls identify a document by name without a visible record-level caller check. Scheduler writes use `ignore_permissions=True`, which is reasonable only within trusted worker paths. |
| Guest / whitelist | OAuth callback is public by protocol but bound to expiring state and owner. Mutating endpoints have ownership checks; diagnostics have role gates. | Bookings operations are whitelisted; app-only functions have no visible role check in their path and use global credentials. Treat as a high-priority authorization review before any compatibility exposure. |
| Tenant isolation | One global tenant/app configuration; no per-resource tenant model. | Same global tenant model; Business ID global uniqueness. A multi-tenant target requires tenant-scoped resource identity and authorization. |
| App-only authorization | No common Graph app-only client identified. Mail's application flow is separate. | Generic app-only Graph helper exists, but Bookings application endpoints need explicit Frappe caller/resource authorization, minimal app roles, and auditability. |
| Retry / throttling | Graph transport handles bounded paging, short `Retry-After`, and one refresh retry on 401; tested. Longer waits defer to a later run. | No explicit retry/backoff/429 handling in inspected Graph wrappers; add common behavior instead of copying transport code. |
| Concurrency / idempotency | Per-calendar lock; delta watermark advances after completed paging; event IDs and push state guard duplicate work. | No sync lock; hash/link dedupe is non-atomic and does not have DB uniqueness on link identity. Appointment create has no idempotency key or local operation record. |
| Setup / consent diagnosis | Doctor and provisioning UI are substantial and tested; Graph capability scopes derive from feature flags. | No doctor; delegated/app-only consent mismatch can surface as generic Graph errors. Bookings needs permission/consent diagnostics. |
| Tests | Broad Graph/calendar/doctor tests and Frappe 15/16 CI. | Business/Event Link tests are empty; one calendar helper test covers an internal save flag, not sync. A migration needs behavioral contract and permission tests first. |

## 11. Recommended target architecture

```text
frappe_microsoft365 (common foundation)
  ├── tenant + application registration configuration
  ├── auth contexts: delegated user / application identity
  ├── Microsoft resource registry (typed, tenant-scoped)
  ├── common Graph transport: paging, retry, throttling, error mapping
  ├── Calendar module: Event sync, recurrence, delta state, ownership
  ├── Teams module: meeting and artifact operations
  ├── optional Bookings module: Business, service/staff/question reads, appointments
  ├── future optional SharePoint module
  └── extension interfaces for downstream app adapters

GRX integration layer
  ├── grx_communication provider adapter and voice-bot mapping
  ├── optional grx_fieldservice Event context adapter
  └── GRX-specific UI, workflows and caller compatibility
```

Keep in common core: tenant/app configuration, delegated and app-only Graph auth contexts, safe token storage, common Graph transport, resource identity/ownership primitives, permission/consent diagnostics, and reusable calendar sync mechanics.

Keep optional: Bookings APIs and DocTypes; Teams features if admins can opt out; future SharePoint. Bookings is a plausible upstream contribution because its resources and workflows are Microsoft-domain capabilities, but its consent and app-only security must be designed with maintainers.

Keep GRX-specific: voice bot configuration, provider requirements/slot speech behavior, `grx_communication` adapter, optional Fieldservice event context, and GRX branding.

Shared/resource calendars require core refactoring: upstream's calendar record currently doubles as user, auth identity and resource. Metadata labels are insufficient. Decide how delegated shared-calendar addressing, room calendars, application permissions, resource ownership, and target Frappe visibility work before implementing.

## 12. Phased contribution / migration plan (not executed)

| Phase | Goal and likely code areas | Risks | Tests required before exit | STOP criteria |
|---|---|---|---|---|
| P0 — architecture alignment | Discuss this analysis, support policy, public extension points, and core-vs-optional module boundary with maintainers | Assumptions from local snapshot may differ from their roadmap; scope creep | Verify findings with maintainers and current upstream HEAD | Stop if no agreement on Frappe-only support, auth/resource direction, or contribution ownership |
| P1 — account/auth/resource model agreement | Design tenant, auth context, resource registry, Frappe owner mapping, consent model; likely core DocTypes and Graph token resolver | Data model churn; permissions accidentally tied to the initiating user; tenant ambiguity | Model-level tests for one identity/multiple resources, delegated and app-only contexts, owner access, tenant isolation | Stop if shared/resource authorization cannot be stated and reviewed or existing calendar behavior regresses |
| P2 — app-only Graph support upstream | Add explicit application token provider and common transport integration, permission diagnostics and audit policy | Privileged app roles can broaden access; confusion with mail's Application flow | Token caching/expiry/secret rotation, scope/role denial, tenant/resource authorization, 401/429 tests | Stop if endpoint authority cannot be restricted or admin-consent requirements are unclear |
| P3 — optional Bookings module | Add Business/resource records, service/staff/questions, requirement builder, availability and create/cancel | API permission breadth, public endpoint abuse, appointment duplicates, tenant/business identity collision | Mocked Graph contract tests, delegated/app-only permission tests, payload/timezone/custom-answer tests, idempotency and authorization tests | Stop if app-only paths remain callable without explicit Frappe authorization or response semantics cannot satisfy caller contract |
| P4 — GRX compatibility adapter | Keep old import/API surface or migrate `grx_communication` coherently; likely GRX adapter package and caller modules | Split behavior across releases; duplicate provider configuration; breaking existing bots | Contract tests for every function/shape listed in section 8; end-to-end import, search, create, cancel | Stop if service IDs, custom requirements, availability slots, or appointment IDs cannot be preserved |
| P5 — shared/resource calendar support | Implement actual delegated shared calendar, room/resource and app-only resource paths; map target Frappe owner | `/me` assumptions; calendar ID access and event visibility; recurrence/delete semantics | Tenant-backed integration coverage plus permission matrix and sync concurrency/delete tests | Stop if metadata is being presented as support without endpoint/auth/owner behavior, or calendar writes could target the wrong resource |
| P6 — data migration / GRX retirement decision | Migrate resource/link/log data, reconnect tokens as needed, dual-run/cutover, then decide whether to retire GRX calendar pieces | Duplicate writes, token outage, event ID loss, ownership drift, rollback complexity | Dry-run reconciliation, duplicate detection, backup/restore, reconnect UX, rollback and cutover rehearsal | Stop on any unmapped event/business ID, ambiguous target user, missing consent, duplicate risk, or caller not migrated |

## 13. Open questions for maintainers

1. Is plain Frappe without ERPNext an explicit supported install target, and should CI prove it independently?
2. Is `Microsoft Calendar` intended to remain one delegated user plus one calendar, or is a resource/auth split on the roadmap?
3. What stable extension API can optional modules use to obtain delegated Graph access without depending on private internals?
4. Is app-only Microsoft Graph support acceptable in core, and how should application roles, admin consent, endpoint authorization, and audit be represented?
5. Would Bookings be an optional module in this repository or a separate Frappe app depending on a stable Graph/auth API?
6. What delegated shared-calendar and app-only room/resource use cases are in scope, and who owns imported Event visibility?
7. Are settings tenant-scoped per site by design, or should multiple Microsoft tenants be supported?
8. Which Event custom fields and sync contracts are stable for downstream apps?
9. Is there an existing public API/schema policy for downstream callers and backward compatibility?
10. What minimum Frappe versions and database migration guarantees apply to optional DocTypes/modules?

## 14. STOP criteria

Do not begin implementation or data retirement until all applicable conditions below are satisfied:

- Maintainers agree on core-vs-optional boundaries, supported Frappe versions, plain-Frappe support, and extension API.
- Delegated and app-only auth contexts, consent, token rotation, tenant isolation, and server-side authorization are explicit and reviewed.
- Calendar resource identity is separated sufficiently to represent multiple calendars per auth identity and resources without a human Microsoft user where required.
- Every GRX capability is mapped to an equivalent, a tested adapter, a migration, or an explicit retirement decision; no capability is silently dropped.
- `grx_communication` contracts and optional `grx_fieldservice` behavior have owners and passing compatibility tests before caller cutover.
- Data mapping covers every Event ID, Bookings Business ID, target user, sync cursor, and relevant audit record; token reconnect/rollback is planned.
- New Bookings app-only endpoints have authorization, idempotency, rate/abuse controls appropriate to their caller, and permission tests.
- Shared/resource calendar claims are supported by implemented endpoint behavior and tenant-backed evidence, not only DocType labels.
- Frappe version matrix, migration rehearsal, and rollback criteria are green before retiring `grx_m365` functionality.

Until these gates are met, keep both repositories' operational data and callers intact. This is a recommendation for preserving reversibility, not a migration instruction.
