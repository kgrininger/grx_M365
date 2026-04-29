import frappe
from frappe.model.document import Document


class M365EventLink(Document):
    def validate(self):
        self.validate_unique_m365_event()

    def validate_unique_m365_event(self):
        if not self.calendar_account or not self.m365_event_id:
            return

        existing = frappe.db.exists(
            "M365 Event Link",
            {
                "calendar_account": self.calendar_account,
                "m365_event_id": self.m365_event_id,
                "name": ["!=", self.name],
            },
        )

        if existing:
            frappe.throw("This Microsoft 365 event is already linked for this calendar account.")