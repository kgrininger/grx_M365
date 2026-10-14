from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from grx_m365.api import calendar_pull
from grx_m365.api.calendar_pull import _save_imported_event


class TestCalendarPullEventPolicy(FrappeTestCase):
	def test_import_save_sets_and_restores_internal_policy_flag(self):
		doc = Mock()
		previous = getattr(frappe.flags, "m365_event_sync", None)

		def insert(**kwargs):
			self.assertTrue(frappe.flags.m365_event_sync)
			self.assertEqual(kwargs, {"ignore_permissions": True})

		doc.insert.side_effect = insert
		_save_imported_event(doc, is_new=True)
		self.assertEqual(getattr(frappe.flags, "m365_event_sync", None), previous)

	def test_update_save_sets_and_restores_internal_policy_flag(self):
		doc = Mock()
		previous = getattr(frappe.flags, "m365_event_sync", None)

		def save(**kwargs):
			self.assertTrue(frappe.flags.m365_event_sync)
			self.assertEqual(kwargs, {"ignore_permissions": True})

		doc.save.side_effect = save
		_save_imported_event(doc)
		self.assertEqual(getattr(frappe.flags, "m365_event_sync", None), previous)

	def test_removed_event_uses_the_trusted_event_adapter(self):
		link_doc = Mock()
		frappe_event = Mock()
		frappe_event.name = "EV-M365-REMOVED"
		frappe_event.subject = "Imported meeting"
		frappe_event.meta.has_field.return_value = True
		with patch.object(calendar_pull.frappe, "get_doc", side_effect=[link_doc, frappe_event]), \
			patch.object(calendar_pull.frappe.db, "exists", return_value=True), \
			patch.object(calendar_pull, "_save_imported_event") as save_adapter:
			calendar_pull.mark_removed_link({"name": "LINK-1", "frappe_event": "EV-M365-REMOVED"})

		save_adapter.assert_called_once_with(frappe_event)
		frappe_event.save.assert_not_called()
		self.assertTrue(link_doc.is_cancelled)
