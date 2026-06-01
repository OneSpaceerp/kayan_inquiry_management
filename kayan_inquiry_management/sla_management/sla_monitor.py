# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

"""SLA monitoring scheduled job.

Runs hourly via scheduler_events in hooks.py.
Checks all active inquiries for SLA breaches and triggers escalations.
"""

import frappe
from frappe import _


def check_sla_breaches():
	"""Check all active inquiries for SLA deadline breaches.

	For each inquiry where an SLA timer is active and the deadline has passed:
	1. Update sla_status to "Breached"
	2. Create an Audit Event
	3. Trigger escalation notification

	This function is called by the Frappe scheduler (hourly).
	"""
	settings = frappe.get_cached_doc("Inquiry Settings")
	if not settings:
		return

	now = frappe.utils.now_datetime()

	# Find inquiries with active SLAs that may be breached
	active_statuses = [
		"New",
		"Pending Review",
		"Assigned to Sales Engineer",
		"Assigned to Application Engineer",
		"Technical Review In Progress",
		"Quotation Preparation In Progress",
	]

	inquiries = frappe.get_all(
		"Inquiry Ticket",
		filters={
			"status": ["in", active_statuses],
			"sla_status": ["in", ["Active", "Not Started"]],
		},
		fields=["name", "status", "sla_assignment_deadline", "sla_technical_deadline", "sla_quotation_deadline"],
	)

	for inquiry in inquiries:
		breached = False

		# Check assignment SLA
		if inquiry.sla_assignment_deadline and now > inquiry.sla_assignment_deadline:
			if inquiry.status in ["New", "Pending Review", "Assigned to Sales Engineer"]:
				breached = True

		# Check technical SLA
		if inquiry.sla_technical_deadline and now > inquiry.sla_technical_deadline:
			if inquiry.status in ["Assigned to Application Engineer", "Technical Review In Progress"]:
				breached = True

		# Check quotation SLA
		if inquiry.sla_quotation_deadline and now > inquiry.sla_quotation_deadline:
			if inquiry.status == "Quotation Preparation In Progress":
				breached = True

		if breached:
			frappe.db.set_value("Inquiry Ticket", inquiry.name, "sla_status", "Breached", update_modified=False)

			# Create audit event for SLA breach
			from kayan_inquiry_management.utils import create_audit_event

			create_audit_event(
				entity_type="Inquiry Ticket",
				entity_id=inquiry.name,
				action="SLA Breached",
				details=f"SLA breached for inquiry {inquiry.name} in status {inquiry.status}",
			)
