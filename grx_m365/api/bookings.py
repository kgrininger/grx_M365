from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import frappe
import requests
from frappe import _

from grx_m365.api.calendar_pull import get_valid_access_token


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


def _s(value: Any) -> str:
    return str(value or "").strip()


def _get_account(account: str):
    if frappe.session.user == "Guest":
        frappe.throw(_("Please login."))

    account = _s(account)
    if not account:
        frappe.throw(_("account is required."))

    account_doc = frappe.get_doc("M365 Account", account)

    if not account_doc.enabled:
        frappe.throw(_("This M365 Account is disabled."))

    return account_doc


def _get_business(bookings_business: str):
    bookings_business = _s(bookings_business)
    if not bookings_business:
        frappe.throw(_("bookings_business is required."))

    doc = frappe.get_doc("M365 Bookings Business", bookings_business)

    if not doc.enabled:
        frappe.throw(_("This M365 Bookings Business is disabled."))

    if not doc.business_id:
        frappe.throw(_("M365 Bookings Business has no business_id."))

    if not doc.m365_account:
        frappe.throw(_("M365 Bookings Business has no linked M365 Account."))

    account_doc = _get_account(doc.m365_account)

    return doc, account_doc


def _headers(account_doc) -> Dict[str, str]:
    access_token = get_valid_access_token(account_doc)

    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Prefer": 'outlook.timezone="W. Europe Standard Time"',
    }


def _graph_request(
    account_doc,
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    response = requests.request(
        method=method.upper(),
        url=f"{GRAPH_BASE_URL}{path}",
        headers=_headers(account_doc),
        params=params,
        json=payload,
        timeout=30,
    )

    if response.status_code >= 400:
        frappe.throw(
            f"Microsoft Graph Bookings API failed: "
            f"{response.status_code} {response.text}"
        )

    if not response.text:
        return {}

    return response.json()


def _graph_get_all(account_doc, path: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    next_url = None
    next_params = params or {}

    while True:
        if next_url:
            response = requests.get(next_url, headers=_headers(account_doc), timeout=30)

            if response.status_code >= 400:
                frappe.throw(
                    f"Microsoft Graph Bookings pagination failed: "
                    f"{response.status_code} {response.text}"
                )

            payload = response.json()
        else:
            payload = _graph_request(account_doc, "GET", path, params=next_params)

        value = payload.get("value") or []
        if isinstance(value, list):
            items.extend(value)

        next_url = payload.get("@odata.nextLink")
        if not next_url:
            break

        next_params = None

    return items


@frappe.whitelist()
def list_businesses(m365_account: str, upsert: int = 0) -> Dict[str, Any]:
    account_doc = _get_account(m365_account)

    businesses = _graph_get_all(account_doc, "/solutions/bookingBusinesses")

    created_or_updated = []
    if int(upsert or 0):
        from grx_m365.grx_m365.doctype.m365_bookings_business.m365_bookings_business import (
            upsert_bookings_business,
        )

        for business in businesses:
            name = upsert_bookings_business(business, m365_account=account_doc.name)
            created_or_updated.append(name)

        frappe.db.commit()

    return {
        "ok": True,
        "m365_account": account_doc.name,
        "count": len(businesses),
        "businesses": businesses,
        "upserted": created_or_updated,
    }


@frappe.whitelist()
def get_business(bookings_business: str) -> Dict[str, Any]:
    business_doc, account_doc = _get_business(bookings_business)

    business = _graph_request(
        account_doc,
        "GET",
        f"/solutions/bookingBusinesses/{business_doc.business_id}",
    )

    return {
        "ok": True,
        "bookings_business": business_doc.name,
        "business_id": business_doc.business_id,
        "business": business,
    }


@frappe.whitelist()
def list_services(bookings_business: str) -> Dict[str, Any]:
    business_doc, account_doc = _get_business(bookings_business)

    services = _graph_get_all(
        account_doc,
        f"/solutions/bookingBusinesses/{business_doc.business_id}/services",
    )

    return {
        "ok": True,
        "bookings_business": business_doc.name,
        "business_id": business_doc.business_id,
        "count": len(services),
        "services": services,
    }

@frappe.whitelist()
def get_service(bookings_business: str, service_id: str) -> Dict[str, Any]:
    business_doc, account_doc = _get_business(bookings_business)

    service_id = _s(service_id)
    if not service_id:
        frappe.throw(_("service_id is required."))

    service = _graph_request(
        account_doc,
        "GET",
        f"/solutions/bookingBusinesses/{business_doc.business_id}/services/{service_id}",
    )

    return {
        "ok": True,
        "bookings_business": business_doc.name,
        "business_id": business_doc.business_id,
        "service_id": service_id,
        "service": service,
    }


@frappe.whitelist()
def get_custom_questions(bookings_business: str) -> Dict[str, Any]:
    business_doc, account_doc = _get_business(bookings_business)

    questions = _graph_get_all(
        account_doc,
        f"/solutions/bookingBusinesses/{business_doc.business_id}/customQuestions",
    )

    return {
        "ok": True,
        "bookings_business": business_doc.name,
        "business_id": business_doc.business_id,
        "count": len(questions),
        "custom_questions": questions,
    }


@frappe.whitelist()
def get_service_booking_requirements(bookings_business: str, service_id: str) -> Dict[str, Any]:
    service_result = get_service(bookings_business, service_id)
    questions_result = get_custom_questions(bookings_business)

    service = service_result.get("service") or {}
    all_questions = questions_result.get("custom_questions") or []

    question_map = {}
    for question in all_questions:
        qid = _s(question.get("id"))
        if qid:
            question_map[qid] = question

    required_fields = [
        {
            "fieldname": "customer_name",
            "label": "Name",
            "required": True,
            "type": "text",
            "source": "standard",
        },
        {
            "fieldname": "customer_email",
            "label": "E-Mail",
            "required": True,
            "type": "email",
            "source": "standard",
        },
        {
            "fieldname": "customer_phone",
            "label": "Telefon",
            "required": False,
            "type": "phone",
            "source": "standard",
        },
    ]

    custom_fields = []
    for link in service.get("customQuestions") or []:
        question_id = _s(link.get("questionId"))
        question = question_map.get(question_id) or {}

        custom_fields.append(
            {
                "question_id": question_id,
                "label": question.get("displayName") or question.get("text") or question_id,
                "required": 1 if link.get("isRequired") else 0,
                "type": question.get("answerInputType") or question.get("type") or "text",
                "source": "customQuestion",
                "raw_link": link,
                "raw_question": question,
            }
        )

    return {
        "ok": True,
        "bookings_business": service_result.get("bookings_business"),
        "business_id": service_result.get("business_id"),
        "service_id": service_id,
        "service_name": service.get("displayName"),
        "default_duration": service.get("defaultDuration"),
        "staff_member_ids": service.get("staffMemberIds") or [],
        "standard_fields": required_fields,
        "custom_fields": custom_fields,
        "raw_service": service,
    }

@frappe.whitelist()
def list_staff_members(bookings_business: str) -> Dict[str, Any]:
    business_doc, account_doc = _get_business(bookings_business)

    staff_members = _graph_get_all(
        account_doc,
        f"/solutions/bookingBusinesses/{business_doc.business_id}/staffMembers",
    )

    return {
        "ok": True,
        "bookings_business": business_doc.name,
        "business_id": business_doc.business_id,
        "count": len(staff_members),
        "staff_members": staff_members,
    }


@frappe.whitelist()
def get_staff_availability(
    bookings_business: str,
    staff_ids: Any,
    start_date_time: str,
    end_date_time: str,
    timezone: Optional[str] = None,
) -> Dict[str, Any]:
    business_doc, account_doc = _get_business(bookings_business)

    start_date_time = _s(start_date_time)
    end_date_time = _s(end_date_time)
    timezone = _s(timezone) or _s(business_doc.default_timezone) or "W. Europe Standard Time"

    if not start_date_time or not end_date_time:
        frappe.throw(_("start_date_time and end_date_time are required."))

    if isinstance(staff_ids, str):
        try:
            staff_ids = json.loads(staff_ids)
        except Exception:
            staff_ids = [staff_ids]

    if not isinstance(staff_ids, list) or not staff_ids:
        frappe.throw(_("staff_ids must be a non-empty list."))

    payload = {
        "staffIds": staff_ids,
        "startDateTime": {"dateTime": start_date_time, "timeZone": timezone},
        "endDateTime": {"dateTime": end_date_time, "timeZone": timezone},
    }

    availability = _graph_request(
        account_doc,
        "POST",
        f"/solutions/bookingBusinesses/{business_doc.business_id}/getStaffAvailability",
        payload=payload,
    )

    return {
        "ok": True,
        "bookings_business": business_doc.name,
        "business_id": business_doc.business_id,
        "availability": availability,
    }


@frappe.whitelist()
def create_appointment(
    bookings_business: str,
    service_id: str,
    start_date_time: str,
    end_date_time: str,
    customer_name: str,
    customer_email: str,
    customer_phone: Optional[str] = None,
    staff_member_ids: Optional[Any] = None,
    timezone: Optional[str] = None,
    notes: Optional[str] = None,
    custom_answers: Optional[Any] = None,
) -> Dict[str, Any]:
    business_doc, account_doc = _get_business(bookings_business)

    service_id = _s(service_id)
    start_date_time = _s(start_date_time)
    end_date_time = _s(end_date_time)
    customer_name = _s(customer_name)
    customer_email = _s(customer_email)
    customer_phone = _s(customer_phone)
    timezone = _s(timezone) or _s(business_doc.default_timezone) or "W. Europe Standard Time"

    if not service_id:
        frappe.throw(_("service_id is required."))
    if not start_date_time or not end_date_time:
        frappe.throw(_("start_date_time and end_date_time are required."))
    if not customer_name:
        frappe.throw(_("customer_name is required."))
    if not customer_email:
        frappe.throw(_("customer_email is required."))

    if isinstance(staff_member_ids, str):
        try:
            staff_member_ids = json.loads(staff_member_ids)
        except Exception:
            staff_member_ids = [staff_member_ids]

    if not isinstance(staff_member_ids, list):
        staff_member_ids = []

    answers = []
    if custom_answers:
        if isinstance(custom_answers, str):
            try:
                answers = json.loads(custom_answers)
            except Exception:
                answers = []
        elif isinstance(custom_answers, list):
            answers = custom_answers

    payload: Dict[str, Any] = {
        "@odata.type": "#microsoft.graph.bookingAppointment",
        "serviceId": service_id,
        "startDateTime": {"dateTime": start_date_time, "timeZone": timezone},
        "endDateTime": {"dateTime": end_date_time, "timeZone": timezone},
        "customers": [
            {
                "@odata.type": "#microsoft.graph.bookingCustomerInformation",
                "name": customer_name,
                "emailAddress": customer_email,
                "phone": customer_phone,
            }
        ],
    }

    if staff_member_ids:
        payload["staffMemberIds"] = staff_member_ids
    if notes:
        payload["customerNotes"] = _s(notes)
    if answers:
        payload["customQuestionAnswers"] = answers

    appointment = _graph_request(
        account_doc,
        "POST",
        f"/solutions/bookingBusinesses/{business_doc.business_id}/appointments",
        payload=payload,
    )

    return {
        "ok": True,
        "bookings_business": business_doc.name,
        "business_id": business_doc.business_id,
        "appointment": appointment,
    }


@frappe.whitelist()
def cancel_appointment(
    bookings_business: str,
    appointment_id: str,
    cancellation_message: Optional[str] = None,
) -> Dict[str, Any]:
    business_doc, account_doc = _get_business(bookings_business)

    appointment_id = _s(appointment_id)
    if not appointment_id:
        frappe.throw(_("appointment_id is required."))

    payload = {}
    if cancellation_message:
        payload["cancellationMessage"] = _s(cancellation_message)

    result = _graph_request(
        account_doc,
        "POST",
        f"/solutions/bookingBusinesses/{business_doc.business_id}/appointments/{appointment_id}/cancel",
        payload=payload,
    )

    return {
        "ok": True,
        "bookings_business": business_doc.name,
        "business_id": business_doc.business_id,
        "appointment_id": appointment_id,
        "result": result,
    }