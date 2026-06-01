# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def create_audit_event(
	entity_type: str,
	entity_id: str,
	action: str,
	details: str | None = None,
) -> None:
	"""Create an immutable Audit Event record.

	Audit events cannot be modified or deleted after creation.
	"""
	frappe.get_doc(
		{
			"doctype": "Audit Event",
			"entity_type": entity_type,
			"entity_id": entity_id,
			"action": action,
			"performed_by": frappe.session.user,
			"performed_on": frappe.utils.now_datetime(),
			"details": details,
		}
	).insert(ignore_permissions=True)


def get_sales_engineer_for_mailbox(mailbox: str) -> str | None:
	"""Look up the Sales Engineer mapped to the given mailbox address."""
	result = frappe.db.get_value(
		"Mailbox Mapping",
		{"mailbox": mailbox, "active": 1},
		"sales_engineer",
	)
	return result


def get_company_for_domain(email_domain: str) -> str | None:
	"""Look up the ERPNext Company mapped to the given email domain."""
	result = frappe.db.get_value(
		"Domain Mapping",
		{"email_domain": email_domain, "active": 1},
		"company",
	)
	return result


def get_inquiry_settings() -> "frappe.Document":
	"""Return the Inquiry Settings singleton document (cached)."""
	return frappe.get_cached_doc("Inquiry Settings")


def calculate_sla_deadline(start_time, sla_hours: int):
	"""Calculate SLA deadline from start time + configurable hours.

	Note: business hours logic will be enhanced in Phase 9.
	Currently uses simple calendar-hour calculation.
	"""
	from datetime import timedelta

	return start_time + timedelta(hours=sla_hours)


# Valid state transitions per Workflow & State Machine Specification §5
VALID_TRANSITIONS: dict[str, list[str]] = {
	"New": ["Pending Review"],
	"Pending Review": ["Assigned to Sales Engineer"],
	"Assigned to Sales Engineer": ["Assigned to Application Engineer", "Cancelled"],
	"Assigned to Application Engineer": ["Technical Review In Progress", "Cancelled"],
	"Technical Review In Progress": ["Quotation Preparation In Progress", "Cancelled"],
	"Quotation Preparation In Progress": ["Pending Approval", "Cancelled"],
	"Pending Approval": ["Approved", "Quotation Preparation In Progress", "Cancelled"],
	"Approved": ["Quotation Sent", "Cancelled"],
	"Quotation Sent": ["Customer Follow-Up", "Cancelled"],
	"Customer Follow-Up": ["Revision Requested", "Won", "Lost", "Cancelled"],
	"Revision Requested": [
		"Technical Review In Progress",
		"Quotation Preparation In Progress",
		"Cancelled",
	],
	"Won": [],
	"Lost": [],
	"Cancelled": [],
}


def validate_status_transition(old_status: str, new_status: str) -> bool:
	"""Check if a status transition is valid per the workflow specification."""
	if old_status == new_status:
		return True
	allowed = VALID_TRANSITIONS.get(old_status, [])
	return new_status in allowed
