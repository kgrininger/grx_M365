import frappe
from frappe.model.document import Document


class M365Account(Document):
    def validate(self):
        if not self.user:
            frappe.throw("User is required.")

        if not self.m365_email:
            frappe.throw("M365 Email is required.")

        self.m365_email = str(self.m365_email or "").strip().lower()

        self.validate_unique_user_email()

    def validate_unique_user_email(self):
        existing = frappe.db.exists(
            "M365 Account",
            {
                "user": self.user,
                "m365_email": self.m365_email,
                "name": ["!=", self.name],
            },
        )

        if existing:
            frappe.throw("This Microsoft 365 account is already connected for this user.")