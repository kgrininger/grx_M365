Production-ready Outlook calendar sync.
Developer-ready Microsoft Bookings connector.

# GRX M365

> Modular Microsoft 365 integration for **Frappe / ERPNext**

`grx_m365` connects Microsoft 365 services with Frappe using the official Microsoft Graph API.

Supports:

- Outlook Calendar Sync
- Shared Calendars
- Includes Microsoft Bookings API connector
- Future Microsoft integrations (Contacts, Mail, Teams, SharePoint)

---

## Why GRX M365?

Many Frappe / ERPNext users work in Microsoft environments.

Existing integrations are often:

- outdated
- Exchange-only
- limited
- complex middleware solutions

**GRX M365** focuses on practical Microsoft 365 integration for Frappe with minimal setup and direct Graph API usage.

---

## Features

### Outlook Calendar

- Microsoft OAuth Login
- Secure token storage
- Automatic token refresh
- Manual sync
- Scheduled sync
- Outlook to Frappe Event sync
- Create / Update / Skip logic
- Duplicate prevention
- Deleted event detection
- Event participants mapping
- Shared calendar support
- Multi-user capable

### Microsoft Bookings

- Sync Bookings Businesses
- Read services metadata
- Staff APIs
- Appointment creation
- Appointment cancellation
- Dynamic booking requirement detection
- Multi-account ready

---

## Architecture

```text
Microsoft 365
├── Outlook Calendar
├── Microsoft Bookings
└── Microsoft Graph API
        ↓
     grx_m365
        ↓
Frappe / ERPNext
```
### Stability

✅ Outlook Calendar: Production Ready  
🟡 Bookings API: Beta / Integration Layer  
🔵 Contacts / Mail / Teams: Planned

---

## Included Doctypes

### M365 Settings

Global Microsoft integration settings.

Fields:

- Tenant ID
- Client ID
- Client Secret
- Redirect URI
- Enabled modules
- Scheduler settings

### M365 Account

Central OAuth-connected Microsoft account.

Stores:

- Microsoft user identity
- Access token
- Refresh token
- Granted scopes
- Token expiry
- Connection status

### M365 Calendar Account

Maps calendars into Frappe.

Fields:

- Linked M365 Account
- Calendar ID
- Calendar Name
- Target User
- Usage Type: Personal, Shared, Team, Resource
- Pull Sync status

### M365 Bookings Business

Synced Microsoft Bookings business.

Fields:

- Linked M365 Account
- Business ID
- Display Name
- Timezone
- Enabled
- Raw Microsoft payload for diagnostics

### M365 Event Link

Maps Outlook events to Frappe Events.

Used for:

- Duplicate prevention
- Update tracking
- Deleted event detection
- Audit trail

### M365 Calendar Sync Log

Sync history and diagnostics.

---

Designed as modular connector layer:
- Use standalone
- Extend in custom apps
- Integrate into GRX workflows

## Installation

Install via Bench CLI:

```bash
cd $PATH_TO_YOUR_BENCH

bench get-app https://github.com/kgrininger/grx_m365.git --branch develop
bench --site yoursite install-app grx_m365
```

---

## Setup

### 1. Microsoft Entra App Registration

Create an App Registration in Microsoft Entra.

Redirect URI:

```text
https://yourdomain.com/api/method/grx_m365.api.auth.callback
```

### 2. API Permissions

Scopes are requested dynamically depending on enabled modules.

Calendar module:

```text
User.Read
Calendars.Read
offline_access
```

Bookings module:

```text
User.Read
BookingsAppointment.ReadWrite.All
offline_access
```

Staff Availability / slot search:

```text
Bookings.Read.All (Application)
```

Server-side appointment creation:

```text
BookingsAppointment.ReadWrite.All (Application)
```

Admin consent is required for Application permissions. Microsoft Graph
`getStaffAvailability` does not support User/Delegated tokens, and server-side
runtime booking can run without a Frappe user session. `grx_m365` therefore uses
`client_credentials` from M365 Settings for app-only Bookings calls and caches
the Application Access Token server-side via `frappe.cache()` only. The
Application Token is not stored in DocTypes.

Admin consent may be required depending on your Microsoft tenant policy.

### 3. Configure M365 Settings

Enter:

- Tenant ID
- Client ID
- Client Secret
- Redirect URI

Then enable the desired modules:

- Calendar
- Bookings

### 4. Connect Microsoft Account

Open:

```text
/api/method/grx_m365.api.auth.connect
```

Login with Microsoft.

This creates or updates an `M365 Account`.

If the Calendar module is enabled, a default `M365 Calendar Account` for the primary calendar is created automatically.

---

## Usage

### Outlook Calendar Sync

Manual sync:

Open a calendar account and click:

```text
Sync Outlook Calendar
```

Or call:

```text
/api/method/grx_m365.api.calendar_pull.sync_account?account=M365-CAL-00001
```

Automatic sync:

```python
scheduler_events = {
    "hourly": [
        "grx_m365.api.scheduler.sync_enabled_calendar_accounts"
    ]
}
```

### Microsoft Bookings

Pull Bookings businesses from Microsoft:

```text
M365 Bookings Business list view
→ Pull Bookings Businesses
→ Select M365 Account
```

Create appointment via API:

```text
grx_m365.api.bookings.create_appointment(...)
```

The Bookings API uses Microsoft Bookings as the scheduling engine. GRX stores references and uses Microsoft Graph for creation, cancellation and service metadata.

---

## Deleted Outlook Events

If an Outlook event disappears inside the configured sync window:

- The event link is flagged as cancelled
- The Frappe Event remains visible for audit/history
- No hard delete is performed by default

---

## Shared Calendars

Supported via:

- Target User
- Calendar Usage
- Calendar ID

Supported usage types:

- Personal
- Shared
- Team
- Resource

---

## Security Notes

- OAuth tokens are stored in `M365 Account`
- Calendar configuration is stored separately in `M365 Calendar Account`
- Bookings configuration is stored separately in `M365 Bookings Business`
- Scopes are requested dynamically based on enabled modules
- The app follows a least-privilege approach where possible

---

## Roadmap

Planned:

- Outlook Push Sync: Frappe to Outlook
- Delta Sync
- Webhooks
- Teams Meeting creation
- Contacts Sync
- Mail Sync
- SharePoint Integration
- GRX Service Case matching
- Lead / CRM integration

---

## Contributing

```bash
cd apps/grx_m365
pre-commit install
```

Recommended tools:

- ruff
- eslint
- prettier
- pyupgrade

---

## License

MIT

---

## Maintainer
This project is open sourced to give the Frappe community a modern Microsoft 365 integration foundation.

Built by **OneTokenSite / Klaus Grininger**

https://onetoken.site
