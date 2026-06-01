# Copyright (c) 2026, Kayan Automation and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from kayan_inquiry_management.utils import VALID_TRANSITIONS


class TestInquiryTicket(IntegrationTestCase):
	"""Integration tests for the Inquiry Ticket DocType.

	Tests cover: CRUD, naming series, status transitions (valid & invalid),
	outcome field validation, SLA timer initialization, and audit trail.
	"""

	def setUp(self):
		"""Create a minimal inquiry ticket for each test."""
		if not frappe.db.exists("Company", "_Test Company"):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": "_Test Company",
					"country": "Egypt",
					"default_currency": "EGP",
				}
			).insert(ignore_permissions=True)

		self.inquiry = frappe.get_doc(
			{
				"doctype": "Inquiry Ticket",
				"company": "_Test Company",
				"priority": "Medium",
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		"""Clean up test inquiry."""
		if frappe.db.exists("Inquiry Ticket", self.inquiry.name):
			frappe.delete_doc("Inquiry Ticket", self.inquiry.name, force=True)

	# ---- Naming & Defaults ----

	def test_naming_series(self):
		"""Verify naming series format INQ-YYYY-XXXXX."""
		self.assertTrue(self.inquiry.name.startswith("INQ-"))

	def test_default_status(self):
		"""New inquiries should default to 'New' status."""
		self.assertEqual(self.inquiry.status, "New")

	def test_default_sla_status(self):
		"""New inquiries should have SLA status 'Active' after insert."""
		# SLA should be started on insert if settings have assignment_sla_hours
		self.assertIn(self.inquiry.sla_status, ["Active", "Not Started"])

	# ---- Valid Status Transitions ----

	def test_valid_transition_new_to_pending_review(self):
		"""New → Pending Review is a valid transition."""
		self.inquiry.status = "Pending Review"
		self.inquiry.save()
		self.assertEqual(self.inquiry.status, "Pending Review")

	def test_valid_transition_pending_review_to_assigned_se(self):
		"""Pending Review → Assigned to Sales Engineer is valid."""
		self.inquiry.status = "Pending Review"
		self.inquiry.save()
		self.inquiry.reload()

		self.inquiry.status = "Assigned to Sales Engineer"
		self.inquiry.save()
		self.assertEqual(self.inquiry.status, "Assigned to Sales Engineer")

	# ---- Invalid Status Transitions ----

	def test_invalid_transition_new_to_won(self):
		"""New → Won should raise an error."""
		self.inquiry.status = "Won"
		self.assertRaises(frappe.ValidationError, self.inquiry.save)

	def test_invalid_transition_new_to_cancelled(self):
		"""New → Cancelled should raise (not in VALID_TRANSITIONS for New)."""
		self.inquiry.status = "Cancelled"
		self.inquiry.cancellation_reason = "Test"
		self.assertRaises(frappe.ValidationError, self.inquiry.save)

	def test_invalid_transition_won_to_anything(self):
		"""Won is a terminal state — no transitions allowed."""
		# Walk the inquiry to Won state
		self._walk_to_status("Won")
		self.inquiry.reload()
		self.inquiry.status = "New"
		self.assertRaises(frappe.ValidationError, self.inquiry.save)

	# ---- Outcome Field Validation ----

	def test_lost_requires_reason(self):
		"""Transition to Lost without lost_reason should raise."""
		self._walk_to_status("Customer Follow-Up")
		self.inquiry.reload()
		self.inquiry.status = "Lost"
		self.assertRaises(frappe.ValidationError, self.inquiry.save)

	def test_cancelled_requires_reason(self):
		"""Transition to Cancelled without cancellation_reason should raise."""
		self._walk_to_status("Assigned to Sales Engineer")
		self.inquiry.reload()
		self.inquiry.status = "Cancelled"
		self.assertRaises(frappe.ValidationError, self.inquiry.save)

	# ---- Status History ----

	def test_status_history_recorded(self):
		"""Status change should create a history record."""
		self.inquiry.status = "Pending Review"
		self.inquiry.save()
		self.inquiry.reload()
		history = [h for h in self.inquiry.status_history if h.new_status == "Pending Review"]
		self.assertTrue(len(history) > 0)

	# ---- Transition Map Completeness ----

	def test_all_states_in_transition_map(self):
		"""Every status option must have an entry in VALID_TRANSITIONS."""
		all_statuses = [
			"New", "Pending Review", "Assigned to Sales Engineer",
			"Assigned to Application Engineer", "Technical Review In Progress",
			"Quotation Preparation In Progress", "Pending Approval", "Approved",
			"Quotation Sent", "Customer Follow-Up", "Revision Requested",
			"Won", "Lost", "Cancelled",
		]
		for status in all_statuses:
			self.assertIn(status, VALID_TRANSITIONS, f"Missing from VALID_TRANSITIONS: {status}")

	def test_terminal_states_have_no_transitions(self):
		"""Won, Lost, Cancelled should have empty transition lists."""
		for terminal in ["Won", "Lost", "Cancelled"]:
			self.assertEqual(
				VALID_TRANSITIONS[terminal], [],
				f"{terminal} should have no outgoing transitions",
			)

	# ---- Helper to walk inquiry through states ----

	def _walk_to_status(self, target_status: str):
		"""Walk the inquiry through valid transitions to reach target_status."""
		# Define shortest paths to each state for testing
		paths = {
			"Pending Review": ["Pending Review"],
			"Assigned to Sales Engineer": ["Pending Review", "Assigned to Sales Engineer"],
			"Assigned to Application Engineer": [
				"Pending Review", "Assigned to Sales Engineer", "Assigned to Application Engineer",
			],
			"Technical Review In Progress": [
				"Pending Review", "Assigned to Sales Engineer",
				"Assigned to Application Engineer", "Technical Review In Progress",
			],
			"Quotation Preparation In Progress": [
				"Pending Review", "Assigned to Sales Engineer",
				"Assigned to Application Engineer", "Technical Review In Progress",
				"Quotation Preparation In Progress",
			],
			"Pending Approval": [
				"Pending Review", "Assigned to Sales Engineer",
				"Assigned to Application Engineer", "Technical Review In Progress",
				"Quotation Preparation In Progress", "Pending Approval",
			],
			"Approved": [
				"Pending Review", "Assigned to Sales Engineer",
				"Assigned to Application Engineer", "Technical Review In Progress",
				"Quotation Preparation In Progress", "Pending Approval", "Approved",
			],
			"Quotation Sent": [
				"Pending Review", "Assigned to Sales Engineer",
				"Assigned to Application Engineer", "Technical Review In Progress",
				"Quotation Preparation In Progress", "Pending Approval",
				"Approved", "Quotation Sent",
			],
			"Customer Follow-Up": [
				"Pending Review", "Assigned to Sales Engineer",
				"Assigned to Application Engineer", "Technical Review In Progress",
				"Quotation Preparation In Progress", "Pending Approval",
				"Approved", "Quotation Sent", "Customer Follow-Up",
			],
			"Won": [
				"Pending Review", "Assigned to Sales Engineer",
				"Assigned to Application Engineer", "Technical Review In Progress",
				"Quotation Preparation In Progress", "Pending Approval",
				"Approved", "Quotation Sent", "Customer Follow-Up", "Won",
			],
		}

		path = paths.get(target_status, [])
		for status in path:
			self.inquiry.reload()
			# Add a dummy assignment when entering AE-related states
			if status == "Assigned to Application Engineer" and not self.inquiry.assignments:
				self.inquiry.append(
					"assignments",
					{
						"user": "Administrator",
						"role_type": "Application Engineer",
						"assigned_by": "Administrator",
						"assigned_on": frappe.utils.now_datetime(),
						"active": 1,
					},
				)
			self.inquiry.status = status
			self.inquiry.save(ignore_permissions=True)
