from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from grx_m365.api import calendar_pull
from grx_m365.api.calendar_pull import _save_imported_event


class TestCalendarPullEventPolicy(FrappeTestCase):
	def setUp(self):
		self.savepoint = "calendar_pull_auth_" + frappe.generate_hash(length=10)
		frappe.db.savepoint(self.savepoint)
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.db.rollback(save_point=self.savepoint)
		frappe.set_user("Administrator")

	def _account(self, *, enabled=0):
		user = frappe.get_doc({
			"doctype": "User", "email": frappe.generate_hash(length=12) + "@example.test",
			"first_name": "Calendar authorization test", "user_type": "System User",
		}).insert(ignore_permissions=True)
		m365_user = frappe.get_doc({
			"doctype": "M365 Account", "user": user.name,
			"m365_email": user.email, "enabled": 1,
		}).insert(ignore_permissions=True)
		account = frappe.get_doc({
			"doctype": "M365 Calendar Account", "m365_account": m365_user.name,
			"calendar_name": "Authorization test", "target_user": user.name,
			"enabled": enabled, "pull_enabled": 1,
		}).insert(ignore_permissions=True)
		return user, account

	def test_sync_account_requires_account_write_before_sync_side_effects(self):
		user, account = self._account(enabled=0)
		frappe.set_user(user.name)
		with patch.object(calendar_pull, "get_m365_account_for_calendar") as get_account:
			with self.assertRaises(frappe.PermissionError):
				calendar_pull.sync_account(account.name)
		get_account.assert_not_called()
		self.assertFalse(frappe.db.exists("M365 Calendar Sync Log", {"calendar_account": account.name}))

	def test_system_manager_passes_account_check_then_observes_disabled_state(self):
		_, account = self._account(enabled=0)
		manager = frappe.get_doc({
			"doctype": "User", "email": frappe.generate_hash(length=12) + "@example.test",
			"first_name": "Calendar admin test", "user_type": "System User",
			"roles": [{"role": "System Manager"}],
		}).insert(ignore_permissions=True)
		frappe.set_user(manager.name)
		with self.assertRaises(frappe.ValidationError):
			calendar_pull.sync_account(account.name)
		self.assertFalse(frappe.db.exists("M365 Calendar Sync Log", {"calendar_account": account.name}))

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
