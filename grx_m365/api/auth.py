import frappe
import requests
from frappe.utils import now_datetime, add_to_date
from urllib.parse import urlencode

from grx_m365.api.graph_client import get_me


AUTHORITY_BASE = "https://login.microsoftonline.com"


def get_settings():
    settings = frappe.get_single("M365 Settings")

    if not settings.enabled:
        frappe.throw("M365 Settings are disabled.")

    if not settings.tenant_id:
        frappe.throw("M365 Tenant ID is missing.")

    if not settings.client_id:
        frappe.throw("M365 Client ID is missing.")

    if not settings.get_password("client_secret"):
        frappe.throw("M365 Client Secret is missing.")

    if not settings.redirect_uri:
        frappe.throw("M365 Redirect URI is missing.")

    return settings


def get_scopes():
    settings = get_settings()

    scopes = [
        "offline_access",
        "User.Read",
    ]

    if settings.enable_calendar:
        scopes.append("Calendars.Read")

    if settings.enable_bookings:
        scopes.append("BookingsAppointment.ReadWrite.All")

    return scopes


@frappe.whitelist()
def connect():
    if frappe.session.user == "Guest":
        frappe.throw("Please login before connecting Microsoft 365.")

    settings = get_settings()

    params = {
        "client_id": settings.client_id,
        "response_type": "code",
        "redirect_uri": settings.redirect_uri,
        "response_mode": "query",
        "scope": " ".join(get_scopes()),
        "state": frappe.session.user,
        "prompt": "select_account",
    }

    url = f"{AUTHORITY_BASE}/{settings.tenant_id}/oauth2/v2.0/authorize?{urlencode(params)}"
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = url


@frappe.whitelist(allow_guest=True)
def callback(code=None, state=None, error=None, error_description=None):
    if error:
        frappe.throw(f"Microsoft OAuth error: {error} - {error_description or ''}")

    if not code:
        frappe.throw("Missing Microsoft OAuth code.")

    if not state:
        frappe.throw("Missing OAuth state.")

    settings = get_settings()

    token_data = exchange_code_for_token(settings, code)
    access_token = token_data.get("access_token")

    if not access_token:
        frappe.throw("Microsoft OAuth did not return an access token.")

    me = get_me(access_token)

    account = upsert_m365_account(
        user=state,
        token_data=token_data,
        me=me,
    )

    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = f"/app/m365-account/{account.name}"


def exchange_code_for_token(settings, code):
    token_url = f"{AUTHORITY_BASE}/{settings.tenant_id}/oauth2/v2.0/token"

    data = {
        "client_id": settings.client_id,
        "client_secret": settings.get_password("client_secret"),
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.redirect_uri,
        "scope": " ".join(get_scopes()),
    }

    response = requests.post(token_url, data=data, timeout=20)

    if response.status_code >= 400:
        frappe.throw(f"Microsoft token exchange failed: {response.status_code} {response.text}")

    return response.json()


def upsert_m365_account(user, token_data, me):
    m365_email = me.get("mail") or me.get("userPrincipalName")
    display_name = me.get("displayName")

    if not m365_email:
        frappe.throw("Microsoft profile did not return an email/userPrincipalName.")

    m365_email = str(m365_email or "").strip().lower()

    existing = frappe.db.get_value(
        "M365 Account",
        {
            "user": user,
            "m365_email": m365_email,
        },
        "name",
    )

    if existing:
        account = frappe.get_doc("M365 Account", existing)
    else:
        account = frappe.new_doc("M365 Account")
        account.user = user
        account.m365_email = m365_email

    account.enabled = 1
    account.display_name = display_name
    account.account_status = "Connected"

    account.access_token = token_data.get("access_token")
    account.refresh_token = token_data.get("refresh_token") or account.get_password("refresh_token")
    account.scope = token_data.get("scope")
    account.last_error = ""

    expires_in = int(token_data.get("expires_in") or 3600)
    account.token_expires_at = add_to_date(now_datetime(), seconds=expires_in - 120)

    account.save(ignore_permissions=True)
    frappe.db.commit()

    ensure_default_calendar_account(account)

    return account


def ensure_default_calendar_account(m365_account):
    settings = frappe.get_single("M365 Settings")

    if not settings.enable_calendar:
        return None

    existing = frappe.db.get_value(
        "M365 Calendar Account",
        {
            "m365_account": m365_account.name,
            "calendar_id": "primary",
        },
        "name",
    )

    if existing:
        calendar = frappe.get_doc("M365 Calendar Account", existing)
    else:
        calendar = frappe.new_doc("M365 Calendar Account")
        calendar.m365_account = m365_account.name
        calendar.calendar_id = "primary"

    calendar.enabled = 1
    calendar.pull_enabled = 1
    calendar.calendar_name = calendar.calendar_name or "Primary Calendar"
    calendar.target_user = calendar.target_user or m365_account.user
    calendar.calendar_usage = calendar.calendar_usage or "Personal"
    calendar.show_in_office_hub = 1
    calendar.sync_status = calendar.sync_status or "Never Synced"

    calendar.save(ignore_permissions=True)
    frappe.db.commit()

    return calendar