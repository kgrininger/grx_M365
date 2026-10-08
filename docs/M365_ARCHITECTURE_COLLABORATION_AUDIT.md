# M365 Architecture & Collaboration Audit

Stand der Codeprüfung: 2026-10-08. Scope ist der Checkout `grx-bench/apps/grx_m365` (Branch `feature/bookings-application-token`) einschließlich App-Code, DocType-Metadaten, Hooks, CI und vorhandener Tests. Code ist Source of Truth. README-Aussagen werden als Zusatzinformation gekennzeichnet, nicht als Beleg für Laufzeitverhalten.

## Kurzfazit

`grx_m365` ist eine Frappe-App ohne deklarierte ERPNext-Abhängigkeit. Sie implementiert delegated OAuth für Microsoft-Benutzer, einen separaten Frappe-Calendar-Account-Datensatz und einen einseitigen Outlook-zu-Frappe-Event-Pull; daneben existiert ein Bookings-Connector mit delegated und app-only Pfaden. Die Kernarchitektur ist jedoch noch nicht als wiederverwendbare Graph-Foundation konsolidiert: Kalender- und Bookings-Code führen eigene HTTP-Aufrufe, Auth-Fehler und Pagination aus. App-only Auth ist im Graph-Helper vorhanden und für Bookings Availability/Appointment APIs benutzt, nicht im Calendar Pull.

Die Felder `Personal / Shared / Team / Resource`, `sync_interval_minutes`, Debug-Setting und Bookings-Verknüpfung mit einem Calendar Account bilden nicht automatisch funktionierende Capabilities. Insbesondere gehen Kalenderabfragen über `/me`, es gibt nur Pull, keine Delta-Cursor, keine Lock-/Retry-Strategie und keine eventbasierten Scheduler-Jobs. Ein Calendar Pull kann ohne interaktive Frappe-Sitzung intern laufen, braucht aber weiterhin ein zuvor autorisiertes delegated Microsoft-Konto und kann bei Bedarf dessen Refresh Token verwenden. Ein Frappe Guest kann den Sync-Endpunkt nicht aufrufen.

## 1. App- und Dependency-Grenzen

- Python-Mindestversion laut `pyproject.toml`: `>=3.10`. Der Workflow `.github/workflows/ci.yml` baut Bench ohne feste Frappe-Version und testet daher gegen den zu diesem Zeitpunkt installierten Standard; im Repository ist keine explizite unterstützte Frappe-Matrix oder v15/v16-Mindestangabe deklariert. CI Python ist 3.10.
- `required_apps` ist auskommentiert/leer. `pyproject.toml` kommentiert Frappe als bench-managed und deklariert keine Python-Runtime-Abhängigkeiten. Direkte Fremdbibliothek: `requests` wird zur Laufzeit importiert, ist aber nicht in `dependencies` deklariert; die Umgebung muss es anderweitig bereitstellen. Frappe ist faktisch Laufzeitvoraussetzung.
- Verwendete Frappe-Komponenten: DocTypes/Document, `frappe.db`, `frappe.get_doc/get_all/new_doc`, Password-Feldzugriff, Whitelist/Session/Response, `frappe.enqueue`, Cache, `frappe.utils`, Tests `FrappeTestCase`, `frappe.log_error`, `frappe.get_installed_apps/get_attr`.
- Kein direkter ERPNext-Import und keine `required_apps`-Kopplung. Der Kalender schreibt in Frappe Core `Event`, `User` und optionale Event-Felder. Das ist Frappe-Core-/Schema-Kopplung, keine ERPNext-Abhängigkeit. Es wird zur Laufzeit optional `grx_fieldservice.api.event_context.resolve_event_context` aufgerufen, wenn `grx_fieldservice` installiert ist. Das ist eine optionale GRX-spezifische Kopplung.
- `grx_communication` nutzt Bookings-Funktionen als dynamischen Python-Vertrag (`api.bookings.list_services`, `get_staff_availability`, `create_appointment_application` bzw. Fallback `create_appointment`). Diese App ist nicht als install-time dependency deklariert.
- GRX-/OTS-spezifisch sind App-Namespace/Branding, optionale Fieldservice-Kontextauflösung und die bestehende Communication-Integration. OAuth, Graph, Kalender und Bookings sind fachlich generische Integrationsbereiche; ihre aktuelle Implementierung ist aber eng an die konkreten M365-DocTypes und Frappe-Event-Form gebunden.
- Versteckte Eigenständigkeitshürden: nicht deklarierte `requests`-Abhängigkeit; OAuth State ist nur Frappe-Username ohne sichtbare Einmaligkeit/Signatur; `Event` Schema wird direkt beschrieben; importierbare Bookings-Python-Funktionen sind extern verwendet; UI-Elemente werden über DocType-Dateien statt über aktive `doctype_js` Hooks geladen (Frappe-Konvention prüfen bei Versionswechsel); die CI pinnt keine Frappe-Generationen.

## 2. Authentifizierung und Account-Modell

### Tatsächliche Objekte

| Ebene | Ist-Modell | Quelle |
|---|---|---|
| Tenant | Ein globales Tenant-ID-Feld in Single DocType `M365 Settings`; keine Tenant-Entität oder tenantbezogene Account-Beziehung | `doctype/m365_settings/m365_settings.json` |
| App Registration | Globale Client ID, Password-Client-Secret und Redirect URI in `M365 Settings` | dito |
| Microsoft Account | `M365 Account` enthält Frappe `user`, normalisierte `m365_email`, Anzeigename, Status, Scope, Tokenablauf und Tokens | `doctype/m365_account/*` |
| Frappe User | Der beim OAuth-Start angemeldete User wird als `state` übergeben und bei Callback ungeprüft zur Account-Verknüpfung verwendet | `api/auth.py` |
| Microsoft User | `/v1.0/me` liefert `mail` oder UPN und Anzeigename. Es gibt keine persistierte Microsoft Object-ID/Tenant-ID pro User | `api/graph_client.py`, `api/auth.py` |
| Calendar | Separater `M365 Calendar Account` Link zu `M365 Account`, Calendar ID, Name, Ziel-Frappe-User, Usage-Auswahl und Pull-Status | `doctype/m365_calendar_account/*` |
| Bookings Business | Separater Datensatz mit Business-ID, M365 Account, Raw JSON, Status-/Metadaten; `business_id` ist global unique | `doctype/m365_bookings_business/*` |

Damit sind Account und Calendar als DocTypes tatsächlich getrennt. Microsoft User und Tenant sind dagegen nur teilweise modelliert: Benutzeridentität ist primär E-Mail/UPN; Tenant ist ein globaler Settings-Wert, kein Attribut am Account. Calendar Usage-Typen sind Auswahlwerte und keine Graph-Ressourcentypen mit eigener Auth-/Owner-Auflösung.

### Auth-Flows und Tokenzustand

- Delegated OAuth 2.0 Authorization Code: `api.auth.connect` ist whitelisted, lehnt Guest ab, fordert `select_account` an und baut authorize URL gegen den festen Tenant. `state` ist aktuell `frappe.session.user`. Callback ist `allow_guest=True`, validiert Vorhandensein von Code und State, aber der sichtbare Code prüft weder State gegen eine gespeicherte Session/Nonce noch Signatur/Einmaligkeit.
- Token-Exchange verwendet Tenant, Client ID/Secret, Code, Redirect URI und dieselben dynamisch zusammengesetzten Scopes. `get_scopes()` fordert `offline_access`, `User.Read`, optional `Calendars.Read`, optional `BookingsAppointment.ReadWrite.All`. Der tatsächlich gewährte Scope-String wird gespeichert. Keine eigenständige Permission-/Feature-Registry, kein expliziter Admin-Consent-Status.
- Upsert identifiziert einen Account über `(Frappe user, lowercased Microsoft email)`. Keine Unique DB Constraints; Controller validiert Duplikate. Microsoft Object ID und Tenant-ID fehlen.
- Access- und Refresh-Tokens werden in `Password`-Feldern von `M365 Account` gespeichert. Refresh passiert bei Calendar Pull, sobald `token_expires_at` abgelaufen/fehlend ist; neue Tokens und Scope werden gespeichert, Ablauf mit 120-Sekunden-Puffer. `M365 Account.last_error/account_status` werden beim Refresh-Fehler nicht systematisch aktualisiert; Calendar Account und Sync Log erhalten den Fehler.
- App-only `client_credentials`: `graph_client.get_application_access_token()` verwendet Settings Tenant, Client ID/Secret und Scope `https://graph.microsoft.com/.default`; Access Token nur in `frappe.cache()` mit TTL `expires_in - 120`, Minimum 60 Sekunden. Keine app-only Refresh Tokens. App-only Graph Request wird von Bookings-Laufzeitfunktionen genutzt.
- Calendar Pull und delegated Bookings teilen `get_valid_access_token()` aus `calendar_pull.py`. App-only-Auswahl geschieht in Bookings explizit durch separate Funktionsvarianten; es gibt keinen einheitlichen Account-/Auth-Resolver.
- Consent muss in Microsoft Entra für delegated Permissions erteilt werden; app-only benötigt konfigurierte Application Permissions und Admin Consent. Der Code erkennt Consent-/Scope-Fehler nur als generische HTTP-Fehler.
- Unbeaufsichtigte Jobs können ein vorhandenes delegated Token verwenden/refreshen und benötigen keine interaktive Frappe-User-Session zur Ausführung. Sie benötigen jedoch Benutzerzustimmung, gültigen Refresh Token, Client Credentials und denselben Tenant. Nur Bookings app-only kann ohne Microsoft User Token arbeiten.

## 3. Graph Client / Abstraktion

- Graph-Aufrufe liegen in `api.graph_client` (`/me`, app-only Token und generischer app-only Request), `api.calendar_pull` (delegated Calendar REST direkt) und `api.bookings` (delegated REST/Pagination plus app-only Helper).
- Kein gemeinsamer Graph Client für beide Auth-Modi. `graph_request_application` deckt nur app-only ab; delegated Requests werden in zwei weiteren Modulen gebaut. Base URL ist jeweils Microsoft Graph `v1.0`.
- Error Handling: HTTP Status >=400 führt zu `frappe.throw` oder generischer Exception und enthält teilweise `response.text` in Fehlermeldung. Keine differenzierte Fehlerklassen oder Status für invalid_grant, consent, not found, transient failures.
- Pagination wird für Calendar `calendarView` und Bookings Collections per `@odata.nextLink` durchlaufen. Kein Seitenlimit/Abbruchschutz.
- Kein expliziter Retry, Backoff, `Retry-After`-/HTTP 429-Handling, Throttling, Circuit Breaker oder Idempotency-Key. Requests haben feste Timeouts.
- Kein Delta API / Delta Link / Cursorpersistenz. Kalender wird in konfiguriertem Rolling Window immer erneut gelesen.
- Service-Pfade: `/me`, `/me/calendarView`, `/me/calendars/{id}/calendarView`; Bookings `/solutions/bookingBusinesses`, `/services`, `/customQuestions`, `/staffMembers`, `/{business}/getStaffAvailability`, `/appointments`, `/{appointment}/cancel`.
- Graph-Schicht ist ein brauchbarer erster app-only Token-Helper, aber heute keine gemeinsame Foundation. Für gemeinsame Nutzung fehlen Auth Context, transport, delegated token provider, Fehler-/Retry-/Pagination-/Throttling-Verhalten, API-/Endpoint Policy und testbare Interfaces.

## 4. Calendar-Modell und Reifegrad

| Capability | Einstufung | Codebefund |
|---|---|---|
| Default / primary Calendar | A/B | Nach OAuth bei aktiviertem Kalender wird `calendar_id=primary` mit Name Primary Calendar und `target_user=account.user` angelegt. Kein Kalenderdiscover-/Picker. |
| Mehrere Kalender | B, eingeschränkt | Mehrere Calendar Account Dokumente sind möglich; IDs müssen manuell gesetzt werden. Fetch nutzt `/me/calendars/{calendar_id}/calendarView`. Kein Shared-Kalender-spezifischer Endpoint oder Discovery. |
| Personal / Shared / Team / Resource | C | Auswahlfeld in Calendar Account; Code verändert Endpoint/Auth/Owner nicht abhängig von Usage. |
| Room | D | Kein eigener Room-Typ oder Graph-Ressourcenpfad. Room-Kalender könnte höchstens manuell als ID versucht werden, Erfolg nicht nachgewiesen. |
| Zielbenutzer / Ownership | B | `target_user` wird Event Owner, fallback auf verknüpften M365 Account User. Teilnehmende werden per E-Mail gegen Frappe User aufgelöst. Microsoft Owner/Object-ID/Calendar Owner Mapping fehlt. |
| Sync-Richtung | B | Ausschließlich Microsoft → Frappe. Keine Frappe → Outlook Writes, keine Event Hook-Registrierung. |
| Event Mapping | B | Subject, Beginn/Ende, Private, Beschreibung aus Preview und Outlook-Link; optional Location/All Day Felder, Teilnehmer und Organizer. Nur Event-Teilnehmer mit passenden Frappe Usern werden übernommen. `sync_with_google_calendar` wird falls vorhanden ausgeschaltet. |
| Recurrence | D/B | Es gibt keine Recurrence-Felder/Expansion/Series- oder Exception-Behandlung im Code. CalendarView kann Graph-Ereignisse liefern, aber fachliche Erhaltung von Serien wird nicht umgesetzt oder getestet. |
| Delete/Cancel | B, eingeschränkt | Graph `isCancelled` markiert vorhandenen Link als cancelled, lässt Event unberührt. Fehlende Events innerhalb des Zeitfensters werden mit `[REMOVED]` markiert und gegebenenfalls auf Closed gesetzt; kein Hard Delete. |
| Dedupe / Update | B | Event Link Schlüssel wird in Controller-Validierung über Calendar Account + Event ID geprüft; SHA-256 Hash überspringt unveränderte Daten. Kein DB Unique Constraint/atomarer Upsert. |
| Conflict Handling | D | Nur Pull überschreibt Eventfelder; keine Konfliktseite, Feldbesitzregeln oder bidirektionale Konfliktbehandlung. |
| State / Cursor | C | Sync-Zeit, Status, Fehler, Fenster und Event Hash sind vorhanden. Kein Delta Token/Cursor. |
| Sync Window | B | Globale Settings 30 Tage zurück / 90 Tage vor, CalendarView jedes Mal; `sync_interval_minutes` wird nicht von Scheduler ausgewertet. |

`A` = im Code erkennbar ausführbar und durch passende Tests abgesichert; `B` = implementiert, aber nur teilweise/ungetestet; `C` = Modell/Felder vorbereitet; `D` = nicht implementiert. Es gibt keine fachlichen Calendar Sync Tests; daher ist kein produktiver Betrieb allein durch den Testbestand belegt.

## 5. Background Jobs

- Aktiver Hook: `hooks.py` registriert stündlich `api.scheduler.sync_enabled_calendar_accounts`. Dieser fragt aktivierte und Pull-aktivierte Accounts ab und enqueued pro Account `api.calendar_pull.sync_account` auf `long`, Timeout 600, `now=False`.
- Queue-Aufruf fängt enqueue-Ausnahmen pro Account ab und schreibt Error Log. Sync selbst protokolliert Lauf in `M365 Calendar Sync Log`, speichert Status/Counters und re-throwt Fehler. Kein automatischer eigener Retry/Backoff nach Fehler.
- Sync-Methode ist zugleich `@frappe.whitelist()` und im Methodenanfang an Guest gebunden. Queue-Worker wird nicht durch einen interaktiven Microsoft- oder Frappe-Benutzerkontext angetrieben; Tokens werden anhand Calendar Account geladen. Die Methode speichert mit `ignore_permissions=True` und macht explizite Commits.
- Delegated Calendar Background Sync funktioniert nur solange gespeicherter Access/Refresh Token für genau den zugeordneten Microsoft-User gültig ist und Client Credentials verfügbar sind. App-only Kalender-Sync fehlt.
- Bookings besitzt keinen Scheduler-/Queue-Job. Die Laufzeit wird synchron durch whitelisted APIs oder durch `grx_communication` aufgerufen; Application Token funktioniert ohne User Session im expliziten app-only Pfad.
- Kein Lock, kein dedupe einer bereits laufenden Queue, keine Concurrent-Sync-Sperre, keine Idempotenz für Jobstart. Event-Upsert ist teilweise idempotent anhand Link/Hash. Monitoring besteht aus Sync Log, DocType-Fehlerfeldern, Frappe Error Log; keine Metriken/Alarmierung.

## 6. Microsoft Bookings

- Account/Auth: Businesses werden einem `M365 Account` zugeordnet und standardmäßig delegated abgefragt. Delegated Scopes werden nur bei `enable_bookings` angefordert (`BookingsAppointment.ReadWrite.All`). App-only Availability und App-only Appointment-Erstellung/-Cancelierung beziehen Client Credentials global aus `M365 Settings`; Business-Resolver der App-only-Varianten prüft Business `enabled` und Business-ID, aber keine Account-Zuordnung.
- Business Import: UI-Aktion in `m365_bookings_business_list.js` fragt M365 Account ab und ruft `list_businesses(..., upsert=1)` auf. `M365 Bookings Business` speichert externe Business-ID, Anzeigename, Account, Zeitzonenfeld, Publish-Flag, last_synced und Raw JSON. Eindeutigkeit ist global nach Business-ID, nicht je Tenant/Account.
- Read APIs: Business, Services, einzelner Service, Custom Questions, Staff Members; Collections paginieren. `get_service_booking_requirements` verbindet Standardfelder (Name, E-Mail, Telefon) mit Service Custom Questions und Required/Type-Metadaten.
- Runtime APIs: Verfügbarkeit (`getStaffAvailability`) über app-only POST; Appointment create/cancel über delegated sowie application Varianten. Payload enthält Kunde, Service, Zeit/Zonen, optionale Staff IDs, Notes, Custom Answers. Es gibt keine lokale Appointment-Persistenz oder regelmäßigen Appointment-Sync.
- Graph-Endpunkte sind in Abschnitt 3 aufgelistet. Kein Update-Appointment, keine lokale Staff-/Service-/Appointment-Entität, keine Webhooks/Delta für Bookings.
- Integration mit `grx_communication`: Booking-Service Import verwendet `list_services`; Runtime verwendet app-only Availability und create-Application (mit delegated Fallback). Das sind bereits relevante externe Contracts.
- Berechtigungsgrenzen: whitelisted Methoden prüfen teilweise nur Guest und Status-Flags; keine expliziten Rollen-/Doc-permission-Checks in API-Funktionen sichtbar. `list_businesses` lädt Account per `get_doc` ohne sichtbare Prüfung, ob der eingeloggte Benutzer der Account-Owner ist. App-only Methoden nehmen keine Frappe Session vorweg, weshalb aufrufende Anwendung und API-Berechtigung besonders relevant sind.
- Einschränkungen: Fehlertexte werden direkt weitergereicht, kein Retry/429; kein Idempotency Key; doppelte Termin-POSTs sind möglich; `default_timezone` wird aus Business-Payload nicht erkennbar korrekt übernommen (Mapping-Code fällt auf bestehenden Wert/default zurück); kein lokales Appointment-Modell. Diese Punkte sind Codebeobachtungen, Laufzeitfolgen nicht in Integrationstests verifiziert.
- Eigenständiges späteres Modul: Bookings Domain/API und deren `M365 Bookings Business` Daten können separat bleiben; Auth Provider, Graph transport, Consent/Permission und Job/diagnostics sollten gemeinsame Foundation nutzen. Die beiden Auth-Arten und Integration mit Communication sind zu bewahren.

## 7. SharePoint / OneDrive

Keine SharePoint-/OneDrive-Implementierung, Settings, DocTypes, Endpunkte, Stubs oder Modulgrenzen im aktiven App-Code gefunden. Nur README Roadmap erwähnt SharePoint. Als tatsächlicher Codebestand: nichts implementiert; keine Architekturvorbereitung nachweisbar.

## 8. Permissions / Security

- Alle sechs eigenen DocTypes haben System Manager CRUD-Rechte laut Metadaten. Tokens sind Password-Felder, Client Secret ebenso. App-only Access Token liegt nur im Frappe Cache.
- Sync schreibt Event, Link und Log mit `ignore_permissions=True`; OAuth legt Account und Default Calendar ebenso mit dieser Option an; Bookings Business Upsert speichert so. Dies ermöglicht Systemoperationen, aber es ist kein Ersatz für autorisierte API-Einstiegspunkte.
- Whitelisted APIs: OAuth `connect` verlangt Login; Callback ist absichtlich Guest-Callable. Calendar Sync verweigert Guest, prüft aber nicht sichtbar `frappe.has_permission` oder Eigentümerschaft des Calendar Accounts. Bookings delegated helper verweigert Guest und Account-disabled, jedoch keine explizite Account-Owner-Prüfung. Diverse Read/Write-Bookings-Methoden sind schlicht `@frappe.whitelist()`.
- App-only Bookings API ist per whitelisted Methoden erreichbar, die `_get_business_for_application` aufrufen; diese kontrolliert Business aktiviert/ID, nicht Benutzer/Role. `create_appointment_application`/Cancel können externe Schreiboperationen auslösen.
- OAuth `state` bindet nur Usernamen und ist nicht gegen CSRF/Replay validiert (Codebefund). Callback speichert Token unter `state` User. Relevantes Sicherheitsrisiko.
- HTTP-Fehlermeldungen enthalten `response.text`; Auth-/Graph-Antwortinhalte und `last_error/error_message` werden nicht redigiert. Kein absichtliches Logging des Tokens gefunden, aber Microsoft Fehlertexte sind nicht als sicher/secret-free garantiert. Beschreibung/Eventfelder enthalten importierte externe Inhalte.
- Tenant Isolation ist schwach: eine globale Tenant/App-Konfiguration pro Site, keine Tenant-ID im Account/Calendar/Bookings-Vertrag, Business-ID global unique. Geeignet für eine einzelne Entra-Tenant-Konfiguration; mehrere Tenants pro Site sind nicht modelliert.

### Risiken aus dem Code

1. Ungeprüfter OAuth State im Guest Callback (CSRF/account-linking Risiko).
2. Whitelisted Bookings-Schreibmethoden und Calendar Sync ohne explizite Objekt-/Rollenberechtigungsprüfung; Account-/Business-Ownership wird nicht gegen Session geprüft.
3. `ignore_permissions=True` wird breit verwendet und verstärkt die Bedeutung korrekter API-Gates.
4. Graph-/Token Fehlertexte werden direkt exponiert/gespeichert.
5. Globale Tenant Settings und fehlende Tenant-Schlüsselung verhindern robuste Mehr-Tenant-Isolation.
6. Frappe Password Felder bieten Framework-Secret-Behandlung; daraus allein lässt sich keine Aussage über Backup-, Schlüsselrotation- oder Deployment-Sicherheit ableiten.

## 9. Setup und Operations

- Installation erfolgt regulär via Bench; keine eigenen Install-/Uninstall-Hooks, keine aktiven Migrationen (`patches.txt` leer). DocTypes werden über Standardmodell-Sync installiert.
- Setup ist manuell: Entra App Registration, Redirect URI, API Permissions, Single Settings mit Tenant/Client/Secret/Redirect und Feature-Schaltern, anschließend User OAuth-Verbindung.
- Setup Doctor/Health Check, Permission-Discovery, Token-Reconnect-Diagnostik, Consent-Erkennung, Graph Connectivity Check und strukturierte Recovery-Aktion sind im Code nicht gefunden. Reconnect-Button im M365 Account öffnet Connect.
- Diagnose: Calendar Sync Log mit Status, Richtung Pull, Zeitfenster, Zählern, JSON Details und Fehler; Account/Calendar haben last error/status. Kein Log-Retention Hook oder Telemetrie.
- Tokenfehler werden beim nächsten Sync erneut versucht; kein Recovery-/Retry-State. Fehlender Refresh Token fordert Reconnect im Fehlertext. Secret/Permission-Änderungen haben keine automatische Cache-Invalidierung für app-only Token; TTL begrenzt den Effekt.
- CI installiert eine nicht festgelegte Frappe-Version auf Python 3.10; keine explizite v15/v16 Matrix. Vorhandene Tests sind leere `FrappeTestCase` Klassen, daher geringe Diagnose-/Kompatibilitätssicherheit.

## 10. Vergleichsstränge und Priorisierung

| Priorität | Thema | Warum vor/bei Foundation-Vergleich |
|---|---|---|
| P0 | Frappe-only Vertrag und ERPNext-Unabhängigkeit | `Event` und `User` sind Frappe Core; keine ERPNext-App darf für M365 Core nötig sein. Prüfen, wie das andere Projekt Events integriert. |
| P0 | Account / Tenant / Microsoft identity Modell | Heute Tenant global, User per E-Mail; gemeinsame Lösung muss klären, ob mehrere Tenants, Microsoft Object IDs und mehrere Konten je User nötig sind. |
| P0 | Delegated OAuth und unattended refresh | Zentraler Calendar Auth-Pfad und Tokenpersistenz müssen mit Scope/Consent und Worker-Verhalten kompatibel sein. |
| P0 | App-only / client credentials | Für Bookings-Runtime bereits reales Erfordernis; muss parallel zu delegated unterstützt werden. |
| P0 | Calendar Account vom Account entkoppeln | Bestehendes preservation requirement und gewünschte Personal/Shared/Team/Resource-Semantik; derzeit nur teilweise runtimewirksam. |
| P0 | Security-/Permission-Modell | Whitelist, Objektbesitz, Guest Callback, CSRF State, System-Manager DocTypes und `ignore_permissions` müssen geklärt werden. |
| P1 | Gemeinsamer Graph Client | Auth Context, Endpunkt-API-Version, Fehler, Pagination, Retry/429 und Throttling sind heute fragmentiert. |
| P1 | Background Jobs und Observability | Stündlicher Calendar Job, Token-Refresh, parallele Ausführung, Recovery und Logs vergleichen. |
| P1 | Calendar Resource Modell und Sync-Semantik | Owner, Shared/Room APIs, Recurrence, Delete, Dedupe, Konflikte, Window vs Delta. |
| P1 | Bookings als Modul | Domain Endpoints und Business Mapping eigenständig halten, aber Foundation Auth/HTTP verwenden; externe `grx_communication` Contracts erhalten. |
| P2 | SharePoint / OneDrive als spätere Module | Derzeit keine Bestands-Capability; nur künftige Modulgrenzen/Permissions können verglichen werden. |
| P2 | Scope-/Permission Registry und Setup Doctor | Früh wünschenswert für Diagnostik, kann modular nach Foundation-Auswahl konkretisiert werden. |

## 11. Foundation-Anforderungen, Upstreaming und Maintainer-Fragen

### Zwingende Eigenschaften einer gemeinsamen Foundation

- Frappe-first und eigenständig installierbar ohne harte ERPNext-Abhängigkeit.
- Saubere Auth Provider für delegated OAuth und app-only client credentials; Token-/Tenant-/User-Kontext nachvollziehbar und background-fähig.
- Microsoft Account darf nicht mit Frappe User oder Kalender gleichgesetzt werden; ein Account kann mehrere Calendars und service-spezifische Konfigurationen tragen.
- Graph Client als klarer, testbarer Service mit Pagination, Fehlerklassifikation, Retry/Retry-After/429, Timeouts und sicherer Protokollierung.
- Consent-/Scope-/Permissionsmodell und Secret Handling, das pro Tenant/Capability diagnostizierbar ist.
- Queue Jobs ohne interaktive Sitzung, mit Idempotenz, Sperren/Parallelitätsregeln, Fehlerzustand und Recovery.
- Öffentliche API-/DocType-Verträge und Datenmigration versioniert; Feature-Module optional.

### Anforderungen aus `grx_m365`

Delegated Calendar Pull mit User Refresh Token; app-only Bookings Runtime; Trennung M365 Account/Calendar; Calendar ID und Frappe Target User; Usage-Labels Personal/Shared/Team/Resource erhalten oder bewusst funktional ersetzen; Bookings Business Import und Service-/Availability-/Appointment API; externer `grx_communication`-Vertrag; Frappe-only Basis; spätere SharePoint-Modularität ermöglichen.

### Vermutlich gut upstreambar

Generic OAuth/Token Provider, Tenant-/Microsoft identity primitives, Graph transport mit Pagination/429/Retry, calendar resource adapters, sichere Job-/Lock-/Log-Primitives, Setup Doctor/Consent Diagnostics und Frappe-Core Event Adapter. Erst nach Vergleich und Maintainer-Abstimmung; dies ist keine Entscheidung für ein Upstream-Ziel.

### Wahrscheinlich modulspezifisch

Microsoft Bookings Business-/Service-/Appointment-Domain, Buchungsportal-Payload-/Requirement-Mapping, `grx_communication` Provider-Kontext, optionale `grx_fieldservice` Event-Context-Auflösung, GRX Office Hub Anzeige-Flag und konkrete Zuordnung zu Frappe Event-/User-Feldern.

### Fragen an `frappe_microsoft365` Maintainers

1. Welche Frappe-Versionen und ERPNext-Annahmen gelten tatsächlich in CI und Runtime? Ist reine Frappe-Installation unterstützt?
2. Wie sind Microsoft Account, Frappe User, Tenant und mehrere Kalender getrennt? Mehrere Entra Tenants pro Site möglich?
3. Gibt es delegated OAuth mit langlebigem Refresh und Jobs ohne angemeldeten User? Wo liegen Tokens und wie wird Rotation/Reconnect behandelt?
4. Gibt es app-only client credentials oder ist das bewusst ausgeschlossen? Können mehrere Auth-Modi koexistieren?
5. Wie sind Shared/Team/Room/Resource Calendars und Calendar Owner/Access aufgelöst?
6. Welche Event-Mapping-, Recurrence-, Delete-, Conflict- und Dedupe-Semantik ist zugesichert?
7. Welcher Graph Client übernimmt Retry, `Retry-After`, Pagination, Delta Cursor und Fehlerklassifikation?
8. Welche Scope-/Consent-Anforderungen gibt es und wie diagnostiziert Setup Doctor fehlerhafte Entra-Konfiguration?
9. Welche DocTypes/APIs gelten als öffentliche Verträge und wie werden Migrationen aus Fremd-Apps behandelt?
10. Wäre Bookings/SharePoint als optionale Service-Module willkommen, ohne den Calendar Kern zu belasten?
11. Wie werden Hintergrundjob Locks, Wiederholungen und Tenant-/User-Isolation umgesetzt?

## Aktuelle Architektur (Ist)

```text
Frappe User ──OAuth state──> M365 Account ──delegated token/refresh──┐
      │                                                            │
      └── M365 Calendar Account (ID, target user, usage labels) ────┤
                                                                   ├─ direct Graph v1.0 calls
M365 Settings (single tenant/client/secret/scopes) ─────────────────┤   ├─ /me/calendarView
      └── client_credentials → graph_client/cache ──────────────────┘   └─ Bookings endpoints
                                                                          │
Hourly hook → enqueue Calendar Pull → Event + M365 Event Link + Sync Log  │
grx_communication ── Python API contract ────────────────────────────────┘
Optional grx_fieldservice event context hook
```

## P0 / P1 / P2-Fragenliste

- **P0:** Frappe-only Installierbarkeit? Tenant-Identität und Schlüsselung? Account/User/Calendar Trennung? Delegated plus app-only? Consent/Scopes? Sicherheits-/Objektberechtigungen? Background Refresh ohne Session? Keine ERPNext-Pflicht?
- **P1:** Graph Client contracts, Retry/429/Pagination/Delta; Calendar Owner/Resource/Semantik; Job Locks/Recovery/Logs; Bookings API/Datenverträge und Communication-Anbindung.
- **P2:** SharePoint/OneDrive Modulvertrag; Setup Doctor Ausbau; spätere zusätzliche M365 Services.

## STOP-Kriterien für spätere Zusammenführung

Eine Zusammenführung nicht starten/freigeben, solange eine der folgenden Fragen offen ist: Frappe-only Basis nicht belegt; delegated Refresh oder Bookings app-only geht verloren; Account-/Calendar-/Tenant-Beziehungen lassen sich nicht verlustfrei abbilden; Calendar Usage-/Owner-Metadaten werden stillschweigend verworfen; Event Delete/Dedupe-/Mapping-Semantik hat keinen Ersatz; Bookings Python-Verträge für `grx_communication` sind gebrochen; Auth-/Scope-/Permission-Unterschiede sind undokumentiert; Tokens/Business IDs/Event Links sind nicht migrierbar; oder Frappe-v15/v16 Unterstützung beruht nur auf Annahme statt Matrix/CI.
