from __future__ import annotations

import json
from typing import Any, Dict, Optional

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class M365BookingsBusiness(Document):
    def validate(self):
        self.business_id = _s(self.business_id)
        self.display_name = _s(self.display_name)

        if not self.business_id:
            frappe.throw("Business ID is required.")

        if not self.default_timezone:
            self.default_timezone = "W. Europe Standard Time"

        if self.m365_account:
            if not frappe.db.exists("M365 Account", self.m365_account):
                frappe.throw(f"M365 Account does not exist: {self.m365_account}")

    def before_save(self):
        if not self.display_name and self.business_id:
            self.display_name = self.business_id

    def update_from_graph(self, data: Dict[str, Any]):
        if not isinstance(data, dict):
            frappe.throw("Bookings business data must be a dict.")

        self.business_id = _s(data.get("id") or self.business_id)
        self.display_name = _s(
            data.get("displayName")
            or data.get("name")
            or self.display_name
            or self.business_id
        )

        self.default_timezone = _s(
            data.get("defaultCurrencyIso")
            and self.default_timezone
            or self.default_timezone
            or "W. Europe Standard Time"
        )

        if self.meta.has_field("is_published"):
            self.is_published = 1 if data.get("isPublished") else 0

        if self.meta.has_field("raw_json"):
            self.raw_json = json.dumps(data, indent=2, ensure_ascii=False, default=str)

        if self.meta.has_field("last_synced_at"):
            self.last_synced_at = now_datetime()


def _s(value: Any) -> str:
    return str(value or "").strip()


def upsert_bookings_business(
    data: Dict[str, Any],
    m365_account: Optional[str] = None,
) -> str:
    business_id = _s(data.get("id"))

    if not business_id:
        frappe.throw("Missing Bookings Business id.")

    existing = frappe.db.get_value(
        "M365 Bookings Business",
        {"business_id": business_id},
        "name",
    )

    if existing:
        doc = frappe.get_doc("M365 Bookings Business", existing)
    else:
        doc = frappe.new_doc("M365 Bookings Business")
        doc.business_id = business_id
        doc.enabled = 1

    if m365_account and doc.meta.has_field("m365_account"):
        doc.m365_account = m365_account

    doc.update_from_graph(data)
    doc.save(ignore_permissions=True)

    return doc.name