# M365 Capability Preservation Audit

Stand: 2026-10-08. Dieses Inventar beschreibt ausschließlich vorhandenen Code und Daten. Es ist ein Preservation-/Regression-Vertrag, keine Zielarchitektur und keine Freigabe zum Löschen. Fundstellen sind relativ zu `grx_m365/`, sofern Repo-Root/`docs/` nicht genannt ist.

## Status-Legende

- **production/working**: belastbar implementiert und fachlich getestet/operativ nachgewiesen.
- **implemented but limited**: Code vorhanden, aber mit Semantik-, Security-, Fehlerbehandlungs- oder Testlücken.
- **experimental**: Runtime-/Integrationspfad ohne ausreichenden Stabilitätsnachweis.
- **prepared only**: Felder/UI/Datenmodell vorhanden, Runtime nicht nachgewiesen.
- **dead/legacy**: nur bei eindeutigen Belegen. Keine Capability wird hier allein wegen fehlender Tests so markiert.

Die zwei vorhandenen `FrappeTestCase` Klassen enthalten jeweils nur `pass`; sie belegen keine Feature-Ausführung. Confidence für fachliche Capabilities ist daher niedrig.

## 1. Capability Inventory

| Capability | Zweck / Fundstelle / DocTypes | Auth / Graph | Frappe-Bezug und Sichtbarkeit | Relevanz, Tests, Status und Grenzen |
|---|---|---|---|---|
| Globale M365-Konfiguration | Tenant, Client ID/Secret, Redirect URI, Modulflags, Sync Window, Intervall-/Debugfelder. `doctype/m365_settings/{json,py}` | Delegated und app-only Konfiguration | Frappe Single DocType; System Manager Desk Settings | Produktiv relevant; Tests fehlen. `sync_interval_minutes` und `debug_enabled` werden in Runtime nicht verwendet. **implemented but limited** |
| OAuth Connect | Delegated Authorization Code Start. `api/auth.py:12-69`, `doctype/m365_account/m365_account.js` | Entra `/authorize`; `offline_access`, `User.Read`, optionale Calendar/Bookings Scopes | Whitelisted, Guest blockiert; Browser Redirect | Wichtig; keine Auth-Tests. `state` ist Frappe Username, keine sichtbare Nonce/CSRF-Verifikation. **implemented but limited** |
| OAuth Callback / Exchange | Code gegen Token tauschen, `/me`, Account Upsert. `api/auth.py:72-165`, `api/graph_client.py:get_me` | Entra `/token`; Graph `/me` | Callback `allow_guest=True`; M365 Account/Calendar | Zentral; Tests fehlen. State wird nicht gegen Session/Signatur/Einmaligkeit geprüft; Fehler geben Response Body weiter. **implemented but limited** |
| M365 Account Identität | Microsoft Mail/UPN, Name, Frappe User, Status, Scopes, Tokenablauf. `doctype/m365_account/*` | Delegated Token Principal | Link zu Frappe User, Password Tokenfelder | Preservation-kritisch. Duplikatprüfung `(user,email)` im Controller, kein DB Unique; keine Microsoft Object ID/Tenant-ID pro Account. **implemented but limited** |
| Token Storage / Refresh | Access-/Refresh-Token Password Felder; Refresh mit Ablaufpuffer. `api/calendar_pull.py:132-177` | OAuth refresh_token grant | Frappe Password API und globale Settings | Produktiv relevant, aber ungetestet. Account Status/last_error werden bei Refreshfehler nicht konsistent gepflegt. **implemented but limited** |
| App-only Token Provider | Client credentials, `.default`, Cache bis kurz vor Ablauf. `api/graph_client.py:26-74` | Entra client_credentials | `frappe.cache()`; Secret aus Settings | Wichtig für Bookings; keine Tests/Invalidierung bei Secretwechsel. **implemented but limited** |
| App-only Graph Request | Generischer App-token Request. `api/graph_client.py:77-103` | Microsoft Graph v1.0 | Frappe + `requests` | Nur app-only, getrennt von delegated Transport. Keine Retry/429. **implemented but limited** |
| Default Calendar Provisioning | OAuth erzeugt primary Calendar Account. `api/auth.py:168-201` | Kein Graph Discovery | `M365 Calendar Account` | Setup-Automation; keine Tests. Primary ID, target User, Personal, Pull enabled. **implemented but limited** |
| Calendar Accounts / mehrere IDs | ID, Name, Zieluser, Usage, Pull-Status. `doctype/m365_calendar_account/*` | Calendar Pull delegated `/me` | Link zu M365 Account und Frappe User | Mehrere Datensätze möglich; keine Discovery/Owner-Validierung. Personal/Shared/Team/Resource sind Datenwerte ohne unterschiedliche Runtime-Pfade. **implemented but limited** |
| Calendar Form Actions | Sync Outlook Calendar und Open M365 Account. `doctype/m365_calendar_account/m365_calendar_account.js` | ruft `api.calendar_pull.sync_account` | Desk-UI, whitelisted API; Guest blockiert | User-visible; kein Test, keine sichtbare Objektberechtigungsprüfung. **implemented but limited** |
| Calendar Sync Window | Default 30 Tage rückwärts/90 vorwärts. `api/calendar_pull.py:24-28`, Settings | Graph calendarView Zeitgrenzen | Frappe Datetime | Datenrelevant; Intervallsetting wird nicht benutzt. **implemented but limited** |
| Calendar Fetch / Pagination | `@odata.nextLink` durchlaufen. `api/calendar_pull.py:180-224` | `/me/calendarView` oder `/me/calendars/{id}/calendarView`, v1.0 | `requests`, delegated token | Keine Tests, Delta, Retry, 429 oder Seitenlimit. `/me` begrenzt Shared-/app-only Modell. **implemented but limited** |
| Event Mapping | Subject, Zeit, Private, Beschreibung aus Preview/Link; optional Location/All Day. `api/calendar_pull.py:353-390,503-543` | Graph Event Felder | Frappe Core `Event`; optionale Event-Felder | Migration-kritisch; keine Tests. Keine Recurrence-/Attachment-/vollständige Body-/Response-Mapping; Zeitzone wird nicht als Originalwert erhalten. **implemented but limited** |
| Event Teilnehmer und Owner | Zieluser/Organizer/Attendees per E-Mail zu Frappe User; Owner neuer Events. `api/calendar_pull.py:353-430,443-459` | Graph Organizer/Attendees | Frappe `User`, Event child table | Unbekannte Microsoft-User werden weggelassen; keine Microsoft-ID-Zuordnung. Keine Tests. **implemented but limited** |
| Dedupe / Update Hash | Link über Calendar+M365 Event ID, SHA-256 Hash skippt unveränderte Events. `api/calendar_pull.py:226-278,461-478`; Event Link DocType | Keine Zusatz-API | Event + M365 Event Link | Preservation-kritisch. Nur Controller-Duplikatprüfung, kein DB Unique/Lock. **implemented but limited** |
| Event Update / Conflict | Bestehendes Frappe Event wird aus Outlook überschrieben. `api/calendar_pull.py:226-278` | Pull | `save(ignore_permissions=True)` | Nur Microsoft→Frappe; keine Feldownership/Konfliktbehandlung. **implemented but limited** |
| Cancel/Delete Handling | `isCancelled` setzt Link cancelled; fehlendes Event im Fenster wird `[REMOVED]`, ggf. Closed. `api/calendar_pull.py:295-353,480-500` | CalendarView Snapshot, kein Delta | Event Link und Frappe Event | Kein Hard Delete. Unvollständige Graph-Liste könnte als Entfernen fehlinterpretiert werden. **implemented but limited** |
| Sync Hash | Hash über ID, Zeit, Text, Location, ChangeKey, Teilnehmer. `api/calendar_pull.py:544-564` | Graph Payload | `hashlib/json` | Interne Dedupe-Funktion, ungetestet; keine Delta-Verknüpfung. **implemented but limited** |
| Sync Log / Status | Laufzeiten, Fenster, Counter, Status, Fehler und JSON. `api/calendar_pull.py:30-119`, Sync Log DocType | Keine | Frappe Log; explizite Commits | Operativ relevant; Fehlertexte ungefiltert, keine Retention/Alerts. **implemented but limited** |
| Hourly Scheduler / Queue | Stündlich enabled/pull_enabled Accounts enqueuen. `hooks.py:245-249`, `api/scheduler.py` | Tokens erst im Job | Frappe scheduler, long queue, Timeout 600 | Aktiv; keine Lock-/Concurrent-Sperre/Retry; Intervallsetting ignoriert. **implemented but limited** |
| Calendar Background Refresh | Queue kann gespeichertes Token lesen/refreshen. `api/calendar_pull.py:15-22,132-177` | Delegated refresh token | Worker ohne interaktive Frappe Session | Unattended nur nach vorherigem User Consent; keine Laufzeittests. **implemented but limited** |
| Optional Fieldservice Context | Nach Event Save optional Kontext auflösen. `api/calendar_pull.py:280-293` | Keine | Dynamischer Call falls `grx_fieldservice` installiert | GRX-spezifisch, Fehler geloggt/ignoriert. **experimental** |
| Bookings Business Import | Graph Businesses listen/upserten; UI-Button. `api/bookings.py:145-169`, List JS, Business DocType | Delegated `/solutions/bookingBusinesses` | Account-Verknüpfung, Frappe DocType | User-visible, Testsuite leer. `business_id` appweit unique statt tenant/account scoped. **implemented but limited** |
| Bookings Business Datenmodell | Business ID, Name, Account, Zeitzone, Published, Raw JSON. `doctype/m365_bookings_business/*` | Graph Business Payload | `M365 Account`; `auth_account` Link auf Calendar Account | `auth_account` wird nicht im API-Pfad genutzt; Timezone Mapping übernimmt keinen erkennbaren Graph-Zonenwert. **implemented but limited** |
| Bookings Metadata Reads | Business, Service, Custom Questions, Staff lesen; Collections paginiert. `api/bookings.py:172-333` | Graph `/solutions/bookingBusinesses/...` | Whitelisted Python API | Keine lokalen Service/Staff Tabellen, keine API-Tests. **implemented but limited** |
| Dynamic Booking Requirements | Standard Name/E-Mail/Telefon plus Service Custom Questions. `api/bookings.py:248-314` | Service + Custom Questions GET | Response für Caller/UI | Keine lokale Persistenz oder Tests. **implemented but limited** |
| Bookings Staff Availability | Staff IDs/Zeit/Zeitzone an Graph senden. `api/bookings.py:334-378` | App-only POST `getStaffAvailability` | Settings client credentials, whitelisted | Kritisch für unattended Runtime; kein sichtbarer Rollencheck; keine Tests. **experimental** |
| Delegated Appointment Create/Cancel | Buchung mit Kunde/Service/Staff/TZ/Notes/Custom Answers; Cancel. `api/bookings.py:380-467,557-587` | Delegated Graph appointments POST/cancel | Account Token, keine lokale Appointment Entität | Keine Idempotency Keys/Tests; doppelte POSTs möglich. **experimental** |
| App-only Appointment Create/Cancel | Gleiche Funktion ohne Microsoft User Token. `api/bookings.py:469-555,589-617` | App-only Graph POST | Client Credentials; Business Resolver prüft enabled/ID | Externe Runtime-Funktion; Whitelist ohne sichtbaren Rollen-/Business-Zugriffsschutz im Funktionspfad. **experimental** |
| Bookings Error / Pagination | Request-Wrapper und nextLink Pagination. `api/bookings.py:74-142` | Graph v1.0 | `requests`, feste Timeouts | Keine Retry/429/Fehlerklassen; Response Body im Fehler. **implemented but limited** |
| `grx_communication` Integration | Service Import und Runtime Availability/Create über M365 Bookings | `../grx_communication/grx_communication/api/v1/appointment_offerings.py`, `appointment_runtime.py` | ruft `list_services`, `get_staff_availability`, `create_appointment_application` (Fallback `create_appointment`) | Reale externe Python-Verträge; keine Integrationstests in dieser App. **implemented but limited** |
| SharePoint / OneDrive | Keine Implementierung, Settings, DocTypes, Stubs oder API gefunden; nur README Roadmap | Gesamte App-Dateisuche | Keine | Keine Bestandsfunktion; Roadmap ist keine Datenmodellvorbereitung. **prepared only** nur als Dokumentationsabsicht |
| Setup / Recovery | Manuelle Settings, Reconnect Button, fehlender Refresh Token fordert Reconnect. Auth/Calendar Code | Entra OAuth | Desk/System Manager | Kein Setup Doctor, Consent Check, Permission Discovery oder Reparaturtool. **implemented but limited** |
| Install-/Migration-Automation | Standard DocType Sync, keine aktiven Patches/Install-Hooks. `patches.txt`, `hooks.py` | Keine | Bench/Frappe | Kein eigener Migrations-/Setup-Code. |

### UI-Funktionen

- `M365 Account`: **Reconnect Microsoft**.
- `M365 Calendar Account`: **Sync Outlook Calendar**, **Open M365 Account**.
- `M365 Bookings Business` List View: **Pull Bookings Businesses**, Account Prompt und Upsert.
- Event Link und Business Form JS enthalten nur auskommentierte Stubs.

## 2. Datenmodell-Inventar

Alle sechs eigenen DocTypes haben System Manager CRUD-Rechte. Bei Migration sind Beziehungen, externe IDs, Status und Sync-Daten gezielt zu bewahren.

| DocType | Zweck und zentrale Felder | Links / Constraints / Status | Zwingend zu erhaltende Information |
|---|---|---|---|
| `M365 Settings` (Single) | enabled, tenant_id, client_id, Password client_secret, redirect_uri, module flags, sync day window, `sync_interval_minutes`, `debug_enabled` | globale Site-Konfiguration, kein Tenant Link an Accounts | Tenant/App Zuordnung, Flags/Fenster. Secret nur über sicheren Transfer oder Reconnect. |
| `M365 Account` | user, m365_email, display_name, account_status, Password access-/refresh_token, token_expires_at, scope, last_error | Link zu Frappe User; Controller uniqueness `(user,email)`, kein DB Unique | User/Microsoft Email, Status, Scope/Expiry/Fehlerzustand. Token nur sicher und gültig migrieren, sonst Reconnect einplanen. |
| `M365 Calendar Account` | m365_account, calendar_id/name, target_user, calendar_usage, show_in_office_hub, pull_enabled, last_sync/success/error/status | Links zu Account und User; IDs nicht unique | Account/Calendar/User Links, Kalender-ID, Usage Labels und Sync Flags. |
| `M365 Event Link` | frappe_event, M365 event id, iCal UID, changeKey, webLink, subject, times, modified, sync_hash, cancelled, last_synced | Link zu Calendar Account und Event; Controller uniqueness Calendar+Event ID, kein DB Unique | Beide Links, alle Microsoft IDs, Hash, Snapshot und Delete/Sync Status. |
| `M365 Calendar Sync Log` | Calendar Account, Zeiten, status/direction, range, counters, error, details_json | Link zu Calendar, Pull-only Statuswerte | Audit-/Recovery-Kontext, sofern Retention beibehalten wird. |
| `M365 Bookings Business` | m365_account, enabled, business_id, display_name, auth_account, default_timezone, is_published, last_synced_at, raw_json | Account Link; optional Calendar Account Link; `business_id` global unique und zugleich autoname | Business-ID, owning account/tenant, enabled, auth_account falls verwendet, timezone, publish, Raw Graph Metadata. |

Keine eigenen Modelle für Tenant, Calendar Resource, Service, Staff, Appointment, Delta Cursor, Graph Subscription, SharePoint Site/Drive oder Consent.

## 3. API- und Integrationsverträge

### Whitelisted Methoden

| Methode | Auth-/Session-Verhalten | Vertrag / Wirkung |
|---|---|---|
| `grx_m365.api.auth.connect` | Guest abgelehnt | OAuth Redirect an Entra |
| `grx_m365.api.auth.callback` | `allow_guest=True` | Token speichern, Account/Default Calendar upserten |
| `grx_m365.api.calendar_pull.sync_account` | Guest abgelehnt; sichtbarer Objektpermission-Check fehlt | Graph Pull, Frappe Event/Link/Log schreiben; UI und Scheduler |
| `grx_m365.api.bookings.list_businesses` | Helper verlangt Login, Account enabled | Business Liste/Upsert; List View |
| `...bookings.get_business` | Login + enabled Business/Account | Graph Business GET |
| `...bookings.list_services` | Login + enabled Business/Account | Graph Service Pagination; externer Communication Caller |
| `...bookings.get_service` | Login + enabled Business/Account | Graph Service GET |
| `...bookings.get_custom_questions` | Login + enabled Business/Account | Graph Custom Question Pagination |
| `...bookings.get_service_booking_requirements` | ruft Read APIs auf | dynamische Requirements Response |
| `...bookings.list_staff_members` | Login + enabled Business/Account | Graph Staff Pagination |
| `...bookings.get_staff_availability` | app-only; kein sichtbarer Rollencheck im Pfad | Graph Availability POST; Communication Runtime |
| `...bookings.create_appointment` | delegated Account Helper | Graph Appointment POST |
| `...bookings.create_appointment_application` | app-only; kein sichtbarer Rollencheck im Pfad | Graph Appointment POST; Communication Runtime |
| `...bookings.cancel_appointment` | delegated Account Helper | Graph Cancel POST |
| `...bookings.cancel_appointment_application` | app-only; kein sichtbarer Rollencheck im Pfad | Graph Cancel POST |

Importierbare, nicht-whitelisted Python Funktionen: `get_valid_access_token`, `refresh_access_token`, `fetch_calendar_view`, `graph_request_application`, `upsert_bookings_business` und Mapping-/Dedupe-Helfer. `grx_communication` nutzt Bookings API-Funktionen als interne App-zu-App-Verträge.

### Hooks, Jobs und Graph Endpunkte

- `hooks.py` stündlich: `api.scheduler.sync_enabled_calendar_accounts`.
- Kein aktiver `doc_events`, `doctype_js`, `override_whitelisted_methods`, `has_permission` oder `permission_query_conditions` Hook.
- Scheduler enqueued `api.calendar_pull.sync_account` je Kalender auf `long`, Timeout 600; keine Bookings Jobs und kein Outbound Calendar Hook.
- Optionaler dynamischer Call auf `grx_fieldservice.api.event_context.resolve_event_context`.
- Externe Endpunkte: Entra authorize/token; Graph `/me`, `/me/calendarView`, `/me/calendars/{id}/calendarView`, Bookings business/service/customQuestions/staffMembers/getStaffAvailability/appointments/cancel.

## 4. Test-Inventar und Confidence

Gefunden: `test_m365_event_link.py` und `test_m365_bookings_business.py`, beide leere `FrappeTestCase` Subklassen. CI führt `bench run-tests --app grx_m365` aus, pinnt aber keine Frappe-Version und hat keine v15/v16 Matrix. Keine Auth-, Calendar-, Graph-Mock-, Bookings- oder End-to-End-Tests.

| Capability | Implementation | Tests | Confidence | Migration Risk |
|---|---|---|---|---|
| OAuth, State, Token Exchange/Refresh | vorhanden | keine | Niedrig | Hoch |
| App-only Token/Cache | vorhanden | keine | Niedrig | Hoch |
| Account/Calendar Modell & Default Provisioning | vorhanden | keine | Niedrig | Hoch |
| Calendar Fetch/Pagination/Window | vorhanden | keine | Niedrig | Hoch |
| Event Mapping/Participants | vorhanden | keine | Niedrig | Hoch |
| Dedupe/Hash/Update | vorhanden | keine | Niedrig | Hoch |
| Cancel/Remove Semantik | vorhanden | keine | Niedrig | Hoch |
| Queue/Scheduler/Logging | vorhanden | keine | Niedrig | Hoch |
| Business Upsert | vorhanden | Testklasse leer | Niedrig | Mittel/Hoch |
| Bookings Reads/Requirements | vorhanden | keine | Niedrig | Mittel |
| Bookings app-only Availability/Create/Cancel | vorhanden | keine | Niedrig | Hoch |
| Communication Integration | Caller vorhanden | keine Integrationstests hier | Niedrig | Hoch |
| SharePoint/OneDrive | nicht vorhanden | nicht zutreffend | Code-Abwesenheit gut belegt | Kein Bestandsverlust |

## 5. Preservation Matrix

Ein Haken bezeichnet einen plausiblen späteren Erhaltungspfad/eine Kategorie, keine bereits getroffene Upstream-Entscheidung. Keine Capability ist als Safe to drop freigegeben.

| Capability | Keep as-is | Could upstream | Could replace with equivalent | Needs adapter/migration | Safe to drop | Unknown / decision |
|---|---:|---:|---:|---:|---:|---:|
| Frappe-only Installierbarkeit / ERPNext-frei | ✓ | ✓ |  |  |  |  |
| Settings inkl. Tenant/App Credentials/Flags |  | ✓ |  | ✓ |  | ✓ |
| Microsoft Account ↔ Frappe User |  | ✓ |  | ✓ |  | ✓ |
| Delegated OAuth/Consent/Refresh |  | ✓ | ✓ | ✓ |  | ✓ |
| App-only Client Credentials/Cache |  | ✓ |  | ✓ |  | ✓ |
| Account vom Calendar getrennt | ✓ | ✓ |  | ✓ |  |  |
| Mehrere Calendars/IDs | ✓ | ✓ | ✓ | ✓ |  |  |
| Personal/Shared/Team/Resource Metadaten | ✓ | ✓ |  | ✓ |  | ✓ |
| Target User/Event Owner Mapping | ✓ |  | ✓ | ✓ |  | ✓ |
| Calendar Pull/Window | ✓ |  | ✓ | ✓ |  |  |
| Event Link/Hash/Dedupe | ✓ | ✓ | ✓ | ✓ |  |  |
| Event Mapping/Teilnehmer | ✓ |  | ✓ | ✓ |  | ✓ |
| Cancelled vs Removed Semantik | ✓ |  | ✓ | ✓ |  | ✓ |
| Sync Logs/Status/Errors | ✓ | ✓ | ✓ | ✓ |  |  |
| Hourly Queue/Delegated Background Refresh | ✓ | ✓ |  | ✓ |  | ✓ |
| Bookings Business Import/Raw JSON | ✓ |  |  | ✓ |  | ✓ |
| Bookings Service/Staff/Question Reads | ✓ |  |  | ✓ |  | ✓ |
| Dynamic Booking Requirements | ✓ |  |  | ✓ |  | ✓ |
| App-only Bookings Availability | ✓ |  |  | ✓ |  | ✓ |
| Delegated + app-only Appointment Create/Cancel | ✓ |  |  | ✓ |  | ✓ |
| `grx_communication` Python-Vertrag | ✓ |  |  | ✓ |  |  |
| Optional Fieldservice Context | ✓ |  |  | ✓ |  | ✓ |
| SharePoint/OneDrive Roadmap |  |  |  |  |  | ✓ |
| DocType/API Permission-Verhalten | ✓ | ✓ |  | ✓ |  | ✓ |

## 6. Regression Gates

Jede relevante Capability muss vor einer späteren Migration einer Aussage zugeordnet und belegt sein:

A. Die gemeinsame Foundation erfüllt sie unverändert;
B. eine neue Implementierung ersetzt sie funktional mit dokumentierter Daten-, API-, Fehler- und Permission-Semantik;
C. sie wird nicht mehr benötigt und ist explizit freigegeben.

Zusätzliche Gates:

1. Account, Calendar, Event Link, Log und Business Beziehungen/IDs/Status sind abgebildet; Tokenmigration ist sicher oder Reconnect ist eingeplant.
2. Delegated Refresh im Queue Worker und app-only Bookings ohne Microsoft User Session funktionieren nachweislich.
3. Calendar Window, Event Mapping, Ownership, Teilnehmer, Dedupe, Cancel und Removal liefern gleiche oder ausdrücklich ersetzte Ergebnisse.
4. `grx_communication` Bookings-Verträge bleiben bestehen oder Caller werden zusammenhängend migriert.
5. Frappe-only Installierbarkeit und unterstützte Frappe-Versionen sind durch CI/Kompatibilitätsangaben belegt.
6. OAuth State, Objektberechtigungen, Guest/Whitelist und Tenant Isolation besitzen dokumentierte Behandlung.
7. Fehlende Tests dürfen nicht als Beleg gelten, dass eine Funktion entbehrlich ist.

**Entscheidungslage:** keine Capability als „Safe to drop“ markiert. Niedrige Test-Confidence erhöht den Nachweisbedarf und ist keine Löschfreigabe.
