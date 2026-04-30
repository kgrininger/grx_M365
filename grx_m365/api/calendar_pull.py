import hashlib
import json
import requests

import frappe
from frappe.utils import now_datetime, add_to_date, get_datetime

from grx_m365.api.auth import AUTHORITY_BASE, get_scopes


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


@frappe.whitelist()
def sync_account(account):
    if frappe.session.user == "Guest":
        frappe.throw("Please login.")

    account_doc = frappe.get_doc("M365 Calendar Account", account)

    if not account_doc.enabled or not account_doc.pull_enabled:
        frappe.throw("This M365 Calendar Account is disabled or pull sync is disabled.")

    settings = frappe.get_single("M365 Settings")
    days_past = int(settings.default_days_past or 30)
    days_future = int(settings.default_days_future or 90)

    range_start = add_to_date(now_datetime(), days=-days_past)
    range_end = add_to_date(now_datetime(), days=days_future)

    log = frappe.new_doc("M365 Calendar Sync Log")
    log.calendar_account = account_doc.name
    log.sync_started_at = now_datetime()
    log.status = "Running"
    log.direction = "Pull"
    log.range_start = range_start
    log.range_end = range_end
    log.insert(ignore_permissions=True)
    frappe.db.commit()

    stats = {
        "seen": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "cancelled": 0,
        "removed": 0,
    }

    try:
        m365_account = get_m365_account_for_calendar(account_doc)
        access_token = get_valid_access_token(m365_account)

        events = fetch_calendar_view(account_doc, access_token, range_start, range_end)

        index = 0
        while index < len(events):
            event = events[index]
            result = upsert_outlook_event(account_doc, event)
            stats["seen"] = stats["seen"] + 1

            if result == "created":
                stats["created"] = stats["created"] + 1
            elif result == "updated":
                stats["updated"] = stats["updated"] + 1
            elif result == "cancelled":
                stats["cancelled"] = stats["cancelled"] + 1
            else:
                stats["skipped"] = stats["skipped"] + 1

            index = index + 1

        stats["removed"] = detect_removed_events(account_doc, events, range_start, range_end)

        account_doc.last_sync_at = now_datetime()
        account_doc.last_success_at = now_datetime()
        account_doc.last_error = ""
        account_doc.sync_status = "Success"
        account_doc.save(ignore_permissions=True)

        log.status = "Success"
        log.sync_finished_at = now_datetime()
        log.events_seen = stats["seen"]
        log.events_created = stats["created"]
        log.events_updated = stats["updated"]
        log.events_skipped = stats["skipped"]
        log.events_cancelled = stats["cancelled"] + stats["removed"]
        log.details_json = json.dumps(stats, indent=2)
        log.save(ignore_permissions=True)

        frappe.db.commit()

        return {
            "ok": True,
            "account": account_doc.name,
            "stats": stats,
        }

    except Exception as exc:
        error_text = str(exc)

        account_doc.last_sync_at = now_datetime()
        account_doc.last_error = error_text
        account_doc.sync_status = "Error"
        account_doc.save(ignore_permissions=True)

        log.status = "Error"
        log.sync_finished_at = now_datetime()
        log.error_message = error_text
        log.events_seen = stats["seen"]
        log.events_created = stats["created"]
        log.events_updated = stats["updated"]
        log.events_skipped = stats["skipped"]
        log.events_cancelled = stats["cancelled"] + stats["removed"]
        log.details_json = json.dumps(stats, indent=2)
        log.save(ignore_permissions=True)

        frappe.db.commit()
        frappe.throw(error_text)

def get_m365_account_for_calendar(calendar_account_doc):
    if not calendar_account_doc.m365_account:
        frappe.throw("M365 Calendar Account has no linked M365 Account.")

    m365_account = frappe.get_doc("M365 Account", calendar_account_doc.m365_account)

    if not m365_account.enabled:
        frappe.throw("Linked M365 Account is disabled.")

    return m365_account

def get_valid_access_token(m365_account_doc):
    expires_at = get_datetime(m365_account_doc.token_expires_at) if m365_account_doc.token_expires_at else None

    if expires_at and expires_at > now_datetime():
        token = m365_account_doc.get_password("access_token")
        if token:
            return token

    return refresh_access_token(m365_account_doc)


def refresh_access_token(m365_account_doc):
    settings = frappe.get_single("M365 Settings")
    refresh_token = m365_account_doc.get_password("refresh_token")

    if not refresh_token:
        frappe.throw("Missing Microsoft refresh token. Please reconnect this account.")

    token_url = f"{AUTHORITY_BASE}/{settings.tenant_id}/oauth2/v2.0/token"

    data = {
        "client_id": settings.client_id,
        "client_secret": settings.get_password("client_secret"),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "redirect_uri": settings.redirect_uri,
        "scope": " ".join(get_scopes())
    }

    response = requests.post(token_url, data=data, timeout=30)

    if response.status_code >= 400:
        frappe.throw(f"Microsoft token refresh failed: {response.status_code} {response.text}")

    token_data = response.json()

    m365_account_doc.access_token = token_data.get("access_token")
    m365_account_doc.refresh_token = token_data.get("refresh_token") or refresh_token
    m365_account_doc.scope = token_data.get("scope") or m365_account_doc.scope

    expires_in = int(token_data.get("expires_in") or 3600)
    m365_account_doc.token_expires_at = add_to_date(now_datetime(), seconds=expires_in - 120)
    m365_account_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return m365_account_doc.get_password("access_token")


def fetch_calendar_view(account_doc, access_token, range_start, range_end):
    calendar_id = account_doc.calendar_id or "primary"

    if calendar_id == "primary":
        url = f"{GRAPH_BASE_URL}/me/calendarView"
    else:
        url = f"{GRAPH_BASE_URL}/me/calendars/{calendar_id}/calendarView"

    params = {
        "startDateTime": range_start.isoformat(),
        "endDateTime": range_end.isoformat(),
        "$top": "50",
        "$orderby": "start/dateTime",
        "$select": "id,subject,bodyPreview,body,start,end,location,webLink,changeKey,iCalUId,lastModifiedDateTime,isCancelled,isAllDay,attendees,organizer",
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Prefer": 'outlook.timezone="Europe/Vienna"',
    }

    events = []
    next_url = url
    next_params = params

    while next_url:
        response = requests.get(next_url, headers=headers, params=next_params, timeout=30)

        if response.status_code >= 400:
            frappe.throw(f"Microsoft calendarView failed: {response.status_code} {response.text}")

        payload = response.json()
        value = payload.get("value") or []

        index = 0
        while index < len(value):
            events.append(value[index])
            index = index + 1

        next_url = payload.get("@odata.nextLink")
        next_params = None

    return events


def upsert_outlook_event(account_doc, outlook_event):
    m365_event_id = outlook_event.get("id")

    if not m365_event_id:
        return "skipped"

    if outlook_event.get("isCancelled"):
        return mark_cancelled(account_doc, outlook_event)

    event_hash = build_event_hash(outlook_event)

    existing_link_name = frappe.db.get_value(
        "M365 Event Link",
        {
            "calendar_account": account_doc.name,
            "m365_event_id": m365_event_id,
        },
        "name",
    )

    if existing_link_name:
        link_doc = frappe.get_doc("M365 Event Link", existing_link_name)

        if link_doc.sync_hash == event_hash and link_doc.frappe_event:
            link_doc.last_synced_at = now_datetime()
            link_doc.save(ignore_permissions=True)
            return "skipped"

        frappe_event = frappe.get_doc("Event", link_doc.frappe_event)
        update_frappe_event(frappe_event, outlook_event, account_doc)
        frappe_event.save(ignore_permissions=True)

        resolve_grx_event_context(frappe_event.name)

        update_link_doc(link_doc, outlook_event, event_hash)
        link_doc.save(ignore_permissions=True)

        return "updated"

    frappe_event = frappe.new_doc("Event")
    update_frappe_event(frappe_event, outlook_event, account_doc)
    frappe_event.insert(ignore_permissions=True)

    resolve_grx_event_context(frappe_event.name)

    link_doc = frappe.new_doc("M365 Event Link")
    link_doc.calendar_account = account_doc.name
    link_doc.frappe_event = frappe_event.name
    update_link_doc(link_doc, outlook_event, event_hash)
    link_doc.insert(ignore_permissions=True)

    return "created"


def resolve_grx_event_context(event_name):
    if "grx_fieldservice" not in frappe.get_installed_apps():
        return

    try:
        frappe.get_attr(
            "grx_fieldservice.api.event_context.resolve_event_context"
        )(event_name)
    except Exception:
        frappe.log_error(
            title="M365 Event context resolve failed",
            message=frappe.get_traceback(),
        )


def detect_removed_events(account_doc, current_events, range_start, range_end):
    current_ids = []

    index = 0
    while index < len(current_events):
        event = current_events[index]
        event_id = event.get("id")
        if event_id:
            current_ids.append(event_id)
        index = index + 1

    links = frappe.get_all(
        "M365 Event Link",
        filters={
            "calendar_account": account_doc.name,
            "is_cancelled": 0,
            "start_time": [">=", range_start],
            "end_time": ["<=", range_end],
        },
        fields=["name", "m365_event_id", "frappe_event", "subject"],
    )

    removed_count = 0

    index = 0
    while index < len(links):
        link = links[index]

        if link.get("m365_event_id") not in current_ids:
            mark_removed_link(link)
            removed_count = removed_count + 1

        index = index + 1

    return removed_count


def mark_removed_link(link):
    link_doc = frappe.get_doc("M365 Event Link", link.get("name"))
    link_doc.is_cancelled = 1
    link_doc.last_synced_at = now_datetime()
    link_doc.save(ignore_permissions=True)

    frappe_event_name = link.get("frappe_event")

    if frappe_event_name and frappe.db.exists("Event", frappe_event_name):
        frappe_event = frappe.get_doc("Event", frappe_event_name)

        subject = frappe_event.subject or ""
        if not subject.startswith("[REMOVED]"):
            frappe_event.subject = "[REMOVED] " + subject

        if frappe_event.meta.has_field("status"):
            frappe_event.status = "Closed"

        frappe_event.save(ignore_permissions=True)


def update_frappe_event(frappe_event, outlook_event, account_doc):
    subject = outlook_event.get("subject") or "(No subject)"

    start_dt = parse_graph_datetime(outlook_event.get("start"))
    end_dt = parse_graph_datetime(outlook_event.get("end"))

    location_data = outlook_event.get("location") or {}
    location = location_data.get("displayName") or ""

    description = build_description(outlook_event)
    target_user = account_doc.get("target_user")

    if not target_user and account_doc.m365_account:
        target_user = frappe.db.get_value("M365 Account", account_doc.m365_account, "user")

    frappe_event.subject = subject
    frappe_event.starts_on = start_dt
    frappe_event.ends_on = end_dt
    frappe_event.event_type = "Private"

    if frappe_event.is_new():
        frappe_event.owner = target_user

    frappe_event.description = description

    if frappe_event.meta.has_field("sync_with_google_calendar"):
        frappe_event.sync_with_google_calendar = 0

    if frappe_event.meta.has_field("location"):
        frappe_event.location = location

    if frappe_event.meta.has_field("all_day"):
        frappe_event.all_day = 1 if outlook_event.get("isAllDay") else 0

    sync_event_participants(frappe_event, outlook_event, account_doc)


def sync_event_participants(frappe_event, outlook_event, account_doc):
    if not frappe_event.meta.has_field("event_participants"):
        return

    target_user = account_doc.get("target_user")

    if not target_user and account_doc.m365_account:
        target_user = frappe.db.get_value("M365 Account", account_doc.m365_account, "user")

    users = []

    add_user_to_list(users, target_user)

    organizer = outlook_event.get("organizer") or {}
    organizer_email = get_graph_email(organizer.get("emailAddress"))
    organizer_user = find_user_by_email(organizer_email)
    add_user_to_list(users, organizer_user)

    attendees = outlook_event.get("attendees") or []
    index = 0
    while index < len(attendees):
        attendee = attendees[index]
        email_address = attendee.get("emailAddress")
        attendee_email = get_graph_email(email_address)
        attendee_user = find_user_by_email(attendee_email)
        add_user_to_list(users, attendee_user)
        index = index + 1

    frappe_event.set("event_participants", [])

    index = 0
    while index < len(users):
        user = users[index]
        frappe_event.append(
            "event_participants",
            {
                "reference_doctype": "User",
                "reference_docname": user,
            },
        )
        index = index + 1


def add_user_to_list(users, user):
    if not user:
        return

    if user in users:
        return

    users.append(user)


def get_graph_email(email_address):
    if not email_address:
        return None

    email = email_address.get("address")
    if not email:
        return None

    return email.strip().lower()


def find_user_by_email(email):
    if not email:
        return None

    return frappe.db.get_value("User", {"email": email}, "name")


def update_link_doc(link_doc, outlook_event, event_hash):
    start_dt = parse_graph_datetime(outlook_event.get("start"))
    end_dt = parse_graph_datetime(outlook_event.get("end"))

    link_doc.m365_event_id = outlook_event.get("id")
    link_doc.m365_ical_uid = outlook_event.get("iCalUId")
    link_doc.m365_change_key = outlook_event.get("changeKey")
    link_doc.m365_web_link = outlook_event.get("webLink")

    link_doc.subject = outlook_event.get("subject") or "(No subject)"
    link_doc.start_time = start_dt
    link_doc.end_time = end_dt
    link_doc.last_modified_datetime = parse_iso_datetime(outlook_event.get("lastModifiedDateTime"))

    link_doc.sync_hash = event_hash
    link_doc.is_cancelled = 1 if outlook_event.get("isCancelled") else 0
    link_doc.last_synced_at = now_datetime()


def mark_cancelled(account_doc, outlook_event):
    m365_event_id = outlook_event.get("id")

    existing_link_name = frappe.db.get_value(
        "M365 Event Link",
        {
            "calendar_account": account_doc.name,
            "m365_event_id": m365_event_id,
        },
        "name",
    )

    if not existing_link_name:
        return "skipped"

    link_doc = frappe.get_doc("M365 Event Link", existing_link_name)
    link_doc.is_cancelled = 1
    link_doc.last_synced_at = now_datetime()
    link_doc.save(ignore_permissions=True)

    return "cancelled"


def parse_graph_datetime(value):
    if not value:
        return None

    date_time = value.get("dateTime")
    if not date_time:
        return None

    return parse_iso_datetime(date_time)


def parse_iso_datetime(value):
    if not value:
        return None

    clean_value = value.replace("Z", "")
    if "." in clean_value:
        clean_value = clean_value.split(".")[0]

    return get_datetime(clean_value)


def build_description(outlook_event):
    body_preview = outlook_event.get("bodyPreview") or ""
    web_link = outlook_event.get("webLink") or ""

    lines = [
        "Imported from Microsoft 365 Outlook Calendar.",
        "",
    ]

    if body_preview:
        lines.append(body_preview)
        lines.append("")

    if web_link:
        lines.append(f"Outlook Link: {web_link}")

    return "\n".join(lines)


def build_event_hash(outlook_event):
    data = {
        "id": outlook_event.get("id"),
        "subject": outlook_event.get("subject"),
        "start": outlook_event.get("start"),
        "end": outlook_event.get("end"),
        "location": outlook_event.get("location"),
        "webLink": outlook_event.get("webLink"),
        "changeKey": outlook_event.get("changeKey"),
        "lastModifiedDateTime": outlook_event.get("lastModifiedDateTime"),
        "isCancelled": outlook_event.get("isCancelled"),
        "isAllDay": outlook_event.get("isAllDay"),
        "bodyPreview": outlook_event.get("bodyPreview"),
        "attendees": outlook_event.get("attendees"),
        "organizer": outlook_event.get("organizer"),
    }

    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()