from unittest.mock import Mock

import frappe
from frappe.tests.utils import FrappeTestCase

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
