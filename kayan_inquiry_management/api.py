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


@frappe.whitelist()
def search_customer(company_name: str = "", email: str = "") -> dict:
	"""Search for an existing Customer by company name or email.

	Returns the first matching customer or empty data list.
	"""
	if not frappe.session.user or frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	filters = []
	if company_name:
		filters.append(["Customer", "customer_name", "like", f"%{company_name}%"])
	if email:
		filters.append(["Customer", "email_id", "=", email])

	if not filters:
		return {"data": []}

	customers = frappe.get_all(
		"Customer",
		or_filters=filters if len(filters) > 1 else None,
		filters=filters if len(filters) == 1 else None,
		fields=["name", "customer_name", "email_id"],
		limit=5,
	)
	return {"data": customers}


@frappe.whitelist()
def search_lead(email: str = "", company_name: str = "") -> dict:
	"""Search for an existing Lead by email or company name.

	Returns the first matching lead or empty data list.
	"""
	if not frappe.session.user or frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	filters = []
	if email:
		filters.append(["Lead", "email_id", "=", email])
	if company_name:
		filters.append(["Lead", "company_name", "like", f"%{company_name}%"])

	if not filters:
		return {"data": []}

	leads = frappe.get_all(
		"Lead",
		or_filters=filters if len(filters) > 1 else None,
		filters=filters if len(filters) == 1 else None,
		fields=["name", "lead_name", "email_id", "company_name"],
		limit=5,
	)
	return {"data": leads}


@frappe.whitelist()
def create_opportunity_for_inquiry(
	opportunity_from: str,
	party_name: str,
) -> dict:
	"""Create an ERPNext Opportunity for an inquiry, using the system default company.

	Args:
		opportunity_from: "Customer" or "Lead"
		party_name: The name (ID) of the Customer or Lead document

	Returns dict with the created Opportunity name and party details.
	"""
	if not frappe.session.user or frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if opportunity_from not in ("Customer", "Lead"):
		frappe.throw(_("opportunity_from must be 'Customer' or 'Lead'"))

	# Use the system default company — avoids hardcoding
	company = frappe.defaults.get_defaults().get("company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)

	opp = frappe.get_doc(
		{
			"doctype": "Opportunity",
			"opportunity_from": opportunity_from,
			"party_name": party_name,
			"company": company,
			"status": "Open",
		}
	)

	# Debugging: Raise an exception with all fields containing '0' or 0
	debug_info = {}
	for key, val in opp.as_dict().items():
		if val in ("0", 0, "0.0", 0.0):
			field = opp.meta.get_field(key)
			debug_info[key] = {
				"value": val,
				"fieldtype": field.fieldtype if field else None,
				"options": field.options if field else None
			}
	frappe.throw(f"DEBUG opp fields: {debug_info}")

	opp.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"name": opp.name,
		"opportunity_from": opp.opportunity_from,
		"party_name": opp.party_name,
		"company": opp.company,
	}


@frappe.whitelist()
def create_lead_for_inquiry(
	lead_name: str,
	company_name: str = "",
	email_id: str = "",
	phone: str = "",
) -> dict:
	"""Create a new Lead for an unknown inquiry sender.

	Returns dict with the created Lead name.
	"""
	if not frappe.session.user or frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	lead = frappe.get_doc(
		{
			"doctype": "Lead",
			"lead_name": lead_name or email_id or "Unknown",
			"company_name": company_name or "",
			"email_id": email_id or "",
			"phone": phone or "",
			"status": "Open",
		}
	)
	# Clean up any invalid "0" or 0 values in Link fields to prevent LinkValidationError
	for key, val in list(lead.as_dict().items()):
		if val in ("0", 0):
			field = lead.meta.get_field(key)
			if field and field.fieldtype == "Link":
				lead.set(key, None)

	for df in lead.meta.get_table_fields():
		for child in lead.get(df.fieldname) or []:
			for key, val in list(child.as_dict().items()):
				if val in ("0", 0):
					field = child.meta.get_field(key)
					if field and field.fieldtype == "Link":
						child.set(key, None)

	lead.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"name": lead.name,
		"lead_name": lead.lead_name,
		"email_id": lead.email_id,
	}


@frappe.whitelist()
def send_sales_engineer_notification(inquiry: str) -> dict:
	"""Send an email/notification to the Sales Engineer assigned to an Inquiry Ticket.

	Called by n8n workflow after a new inquiry ticket is created.
	If no specific engineer is assigned, notifies all users with the Sales Engineer role.
	"""
	if not frappe.session.user or frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Inquiry Ticket", inquiry)

	# Determine recipients
	recipients = []
	if doc.sales_engineer:
		engineer_email = frappe.db.get_value("User", doc.sales_engineer, "email")
		if engineer_email:
			recipients.append(engineer_email)
	else:
		# Notify all active Sales Engineers
		engineers = frappe.get_all(
			"Has Role",
			filters={"role": "Sales Engineer", "parenttype": "User"},
			fields=["parent as user"],
		)
		for eng in engineers:
			email = frappe.db.get_value("User", eng.user, "email")
			if email and frappe.db.get_value("User", eng.user, "enabled"):
				recipients.append(email)

	if not recipients:
		return {"status": "skipped", "reason": "No Sales Engineer recipients found"}

	subject = f"New Inquiry Ticket: {doc.name} - {doc.company_name or ''}"
	message = frappe.render_template(
		"""<p>A new inquiry ticket has been created and requires your attention.</p>
<table style="border-collapse:collapse; width:100%">
  <tr><td style="padding:4px 8px; font-weight:bold">Ticket</td><td style="padding:4px 8px">{{ doc.name }}</td></tr>
  <tr><td style="padding:4px 8px; font-weight:bold">Company</td><td style="padding:4px 8px">{{ doc.company_name or '-' }}</td></tr>
  <tr><td style="padding:4px 8px; font-weight:bold">Subject</td><td style="padding:4px 8px">{{ doc.original_email_subject or '-' }}</td></tr>
  <tr><td style="padding:4px 8px; font-weight:bold">Type</td><td style="padding:4px 8px">{{ doc.inquiry_type or '-' }}</td></tr>
  <tr><td style="padding:4px 8px; font-weight:bold">Status</td><td style="padding:4px 8px">{{ doc.status }}</td></tr>
</table>
<br>
<a href="{{ frappe.utils.get_url() }}/{{ doc.doctype }}/{{ doc.name }}">Open Ticket</a>""",
		{"doc": doc},
	)

	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=message,
		reference_doctype="Inquiry Ticket",
		reference_name=doc.name,
	)

	return {"status": "sent", "recipients": recipients, "ticket": doc.name}

