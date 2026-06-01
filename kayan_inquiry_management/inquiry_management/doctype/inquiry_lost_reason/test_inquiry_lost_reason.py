# Copyright (c) 2026, Kayan Automation and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestInquiryLostReason(IntegrationTestCase):
	def test_create_lost_reason(self):
		doc = frappe.get_doc(
			{"doctype": "Inquiry Lost Reason", "reason_name": "Test Reason", "active": 1}
		).insert()
		self.assertEqual(doc.reason_name, "Test Reason")
		self.assertEqual(doc.active, 1)
		doc.delete()
