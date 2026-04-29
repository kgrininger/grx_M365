# GRX M365

Microsoft 365 Calendar integration for **Frappe / ERPNext**.

`grx_m365` connects Microsoft Outlook calendars with Frappe `Event` records using Microsoft Graph API.

---

# Features

## Current Version (MVP)

✅ Microsoft 365 OAuth Login
✅ Secure token storage
✅ Automatic token refresh
✅ Manual sync per calendar account
✅ Scheduler / automatic sync
✅ Outlook Calendar → Frappe Event sync
✅ Create / Update / Skip logic
✅ No duplicate events
✅ Deleted Outlook events detected
✅ Event participants from internal users
✅ Multi-user capable
✅ Shared calendar ready (Target User mapping)

---

# Architecture

```text
Microsoft Outlook Calendar
        ↓
Microsoft Graph API
        ↓
grx_m365
        ↓
Frappe Event
```

---

# Included Doctypes

## M365 Settings

Global Microsoft connection settings.

Fields:

* Tenant ID
* Client ID
* Client Secret
* Redirect URI
* Default Sync Window
* Scheduler Settings

---

## M365 Calendar Account

One connected Microsoft calendar account.

Fields:

* User
* Target User
* Calendar ID
* Calendar Type
* OAuth Tokens
* Sync Status

---

## M365 Event Link

Maps Outlook Events to Frappe Events.

Used for:

* duplicate prevention
* updates
* deleted event detection

---

## M365 Calendar Sync Log

Sync history and diagnostics.

---

# Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/YOURUSER/grx_m365.git --branch develop
bench --site yoursite install-app grx_m365
```

---

# Setup

## 1. Microsoft Entra App Registration

Create an App Registration.

Redirect URI:

```text
https://yourdomain.com/api/method/grx_m365.api.auth.callback
```

Permissions:

```text
User.Read
Calendars.Read
offline_access
```

---

## 2. Configure M365 Settings

Enter:

* Tenant ID
* Client ID
* Client Secret
* Redirect URI

Enable integration.

---

## 3. Connect User Account

Open:

```text
/api/method/grx_m365.api.auth.connect
```

Login with Microsoft.

---

# Sync

## Manual Sync

Open a calendar account and click:

```text
Sync Outlook Calendar
```

or call:

```text
/api/method/grx_m365.api.calendar_pull.sync_account?account=M365-CAL-00001
```

## Automatic Sync

Scheduler supported.

Example:

```python
scheduler_events = {
    "hourly": [
        "grx_m365.api.scheduler.sync_enabled_calendar_accounts"
    ]
}
```

---

# Deleted Events

If an Outlook event disappears inside the configured sync window:

* Event is marked as removed
* Link is flagged cancelled
* Frappe event remains visible for audit/history

No hard delete by default.

---

# Shared Calendars

Supported via:

```text
Target User
Calendar Usage
```

Examples:

* Personal
* Shared
* Team
* Resource

---

# Contributing

This app uses `pre-commit` for code formatting and linting.

```bash
cd apps/grx_m365
pre-commit install
```

Configured tools:

* ruff
* eslint
* prettier
* pyupgrade

---

# CI

Recommended GitHub Actions setup:

* CI: install app + run tests on pushes to `develop`
* Linters: Semgrep + pip-audit on pull requests

---

# Roadmap

## Planned

* Push sync (Frappe → Outlook)
* Delta Sync
* Webhooks
* Teams Meeting support
* SharePoint integration
* Contact / Lead matching
* Service Case linking

---

# Why this App?

Many Frappe users need Microsoft 365 integration.

This app provides a clean, lightweight, open solution without heavy external middleware.

---

# License

MIT

---

# Maintainer

Built by onetoken.site / Klaus Grininger
