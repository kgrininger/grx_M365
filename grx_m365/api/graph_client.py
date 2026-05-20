import frappe
import requests


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
AUTHORITY_BASE = "https://login.microsoftonline.com"
APPLICATION_SCOPE = "https://graph.microsoft.com/.default"


def get_me(access_token):
    response = requests.get(
        f"{GRAPH_BASE_URL}/me",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=20,
    )

    if response.status_code >= 400:
        raise Exception(f"Microsoft Graph /me failed: {response.status_code} {response.text}")

    return response.json()


def get_application_access_token():
    settings = frappe.get_single("M365 Settings")

    if not settings.enabled:
        frappe.throw("M365 Settings are disabled.")

    tenant_id = _clean(settings.tenant_id)
    client_id = _clean(settings.client_id)
    client_secret = settings.get_password("client_secret")

    if not tenant_id:
        frappe.throw("M365 Settings tenant_id is required.")
    if not client_id:
        frappe.throw("M365 Settings client_id is required.")
    if not client_secret:
        frappe.throw("M365 Settings client_secret is required.")

    cache_key = f"grx_m365:application_access_token:{tenant_id}:{client_id}"
    cached_token = frappe.cache().get_value(cache_key)
    if cached_token:
        return cached_token

    response = requests.post(
        f"{AUTHORITY_BASE}/{tenant_id}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": APPLICATION_SCOPE,
        },
        timeout=30,
    )

    if response.status_code >= 400:
        frappe.throw(
            f"Microsoft application token request failed: "
            f"{response.status_code} {response.text}"
        )

    token_data = response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        frappe.throw("Microsoft application token response did not include access_token.")

    expires_in = _to_int(token_data.get("expires_in"), 3600)
    ttl = max(60, expires_in - 120)
    frappe.cache().set_value(cache_key, access_token, expires_in_sec=ttl)

    return access_token


def graph_request_application(method, path, params=None, payload=None):
    access_token = get_application_access_token()

    response = requests.request(
        method=method.upper(),
        url=f"{GRAPH_BASE_URL}{path}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Prefer": 'outlook.timezone="W. Europe Standard Time"',
        },
        params=params,
        json=payload,
        timeout=30,
    )

    if response.status_code >= 400:
        frappe.throw(
            f"Microsoft Graph Application API failed: "
            f"{response.status_code} {response.text}"
        )

    if not response.text:
        return {}

    return response.json()


def _clean(value):
    return str(value or "").strip()


def _to_int(value, default):
    try:
        return int(value or 0)
    except Exception:
        return default
