# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

import frappe
from frappe import _


@frappe.whitelist()
def get_inquiry_summary(inquiry_name: str) -> dict:
	"""Return a summary of the inquiry ticket for dashboard display."""
	if not frappe.has_permission("Inquiry Ticket", "read", inquiry_name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_cached_doc("Inquiry Ticket", inquiry_name)
	return {
		"name": doc.name,
		"status": doc.status,
		"company_name": doc.company_name,
		"sales_engineer": doc.sales_engineer,
		"priority": doc.priority,
		"inquiry_type": doc.inquiry_type,
		"estimated_value": doc.estimated_value,
		"revision_count": doc.revision_count,
		"sla_status": doc.sla_status,
	}


@frappe.whitelist()
def create_erpnext_quotation(inquiry_name: str) -> str:
	"""Generate an ERPNext Quotation from an approved Inquiry Ticket.

	Returns the name of the created Quotation.
	"""
	if not frappe.has_permission("Inquiry Ticket", "write", inquiry_name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Inquiry Ticket", inquiry_name)

	if doc.status != "Approved":
		frappe.throw(_("Inquiry must be in Approved status to generate a quotation."))

	if not doc.customer:
		frappe.throw(_("A linked Customer is required to create a quotation."))

	# Build quotation items from inquiry line items
	items = []
	for line in doc.line_items:
		items.append(
			{
				"item_code": line.item if line.item else None,
				"description": line.item_description,
				"qty": line.quantity or 1,
				"uom": line.uom or "Nos",
			}
		)

	if not items:
		frappe.throw(_("At least one line item is required to create a quotation."))

	quotation = frappe.get_doc(
		{
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": doc.customer,
			"company": doc.company,
			"items": items,
		}
	)
	quotation.insert(ignore_permissions=True)

	# Link quotation back to inquiry
	doc.db_set("current_quotation", quotation.name, update_modified=False)
	doc.db_set("quotation_count", (doc.quotation_count or 0) + 1, update_modified=False)

	frappe.msgprint(_("Quotation {0} created successfully.").format(quotation.name))
	return quotation.name


@frappe.whitelist()
def create_revision(inquiry_name: str, reason: str) -> dict:
	"""Create a new revision record on an Inquiry Ticket."""
	if not frappe.has_permission("Inquiry Ticket", "write", inquiry_name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Inquiry Ticket", inquiry_name)
	revision_no = (doc.revision_count or 0) + 1

	doc.append(
		"revisions",
		{
			"revision_no": revision_no,
			"revision_reason": reason,
			"requested_by": frappe.session.user,
			"requested_on": frappe.utils.now_datetime(),
			"status": "Requested",
		},
	)
	doc.revision_count = revision_no
	doc.save(ignore_permissions=True)

	return {"revision_no": revision_no, "status": "Requested"}


@frappe.whitelist(allow_guest=True)
def inspect_headers() -> dict:
	"""Inspect request headers."""
	return dict(frappe.request.headers) if hasattr(frappe, "request") and frappe.request else {}


@frappe.whitelist()
def get_ai_settings() -> dict:
	"""Return AI configuration settings including decrypted API key."""
	if not frappe.session.user or frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	settings = frappe.get_doc("Inquiry Settings")
	return {
		"confidence_threshold": settings.confidence_threshold or 75,
		"default_ai_provider": settings.default_ai_provider,
		"preferred_language": settings.preferred_language or "English",
		"ai_api_url": settings.ai_api_url,
		"ai_api_key": settings.get_password("ai_api_key") if settings.ai_api_key else None
	}


