# Copyright (c) 2026, Kayan Automation and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestInquirySettings(IntegrationTestCase):
	def test_default_values(self):
		"""Verify that Inquiry Settings returns sensible defaults."""
		settings = frappe.get_single("Inquiry Settings")
		self.assertEqual(settings.assignment_sla_hours, 4)
		self.assertEqual(settings.technical_sla_hours, 24)
		self.assertEqual(settings.quotation_sla_hours, 48)
		self.assertEqual(settings.confidence_threshold, 75)

	def test_invalid_confidence_threshold(self):
		"""Confidence threshold outside 0–100 should raise."""
		settings = frappe.get_single("Inquiry Settings")
		settings.confidence_threshold = 150
		self.assertRaises(frappe.ValidationError, settings.save)

	def test_invalid_sla_hours(self):
		"""SLA hours less than 1 should raise."""
		settings = frappe.get_single("Inquiry Settings")
		settings.assignment_sla_hours = 0
		self.assertRaises(frappe.ValidationError, settings.save)
