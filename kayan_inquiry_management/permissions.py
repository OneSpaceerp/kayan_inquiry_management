# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def inquiry_ticket_query_conditions(user):
	"""Return SQL conditions for company-based filtering of Inquiry Tickets.

	- System Manager and CEO: see all companies
	- Other roles: see only companies assigned to the user
	- Sales Engineer: see only owned inquiries (within their companies)
	- Application Engineer: see only assigned inquiries (within their companies)
	"""
	if not user:
		user = frappe.session.user

	if user == "Administrator":
		return ""

	roles = frappe.get_roles(user)

	# Full access roles
	if "System Manager" in roles or "CEO" in roles:
		return ""

	# Company-level access
	user_companies = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Company"},
		pluck="for_value",
	)

	if not user_companies:
		# Fallback: user has no company restrictions, allow all
		return ""

	companies_str = ", ".join(f"'{c}'" for c in user_companies)
	conditions = f"`tabInquiry Ticket`.company IN ({companies_str})"

	# Sales Engineer: further restrict to owned inquiries (unless Sales Manager+)
	if "Sales Engineer" in roles and "Sales Manager" not in roles:
		conditions += f" AND `tabInquiry Ticket`.sales_engineer = '{user}'"

	return conditions


def inquiry_ticket_has_permission(doc, ptype, user):
	"""Check whether a user has permission to access a specific Inquiry Ticket.

	Enforces ownership-based and assignment-based visibility per RPM §10.
	"""
	if not user:
		user = frappe.session.user

	if user == "Administrator":
		return True

	roles = frappe.get_roles(user)

	# Full access roles
	if "System Manager" in roles or "CEO" in roles:
		return True

	# Check company access
	user_companies = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Company"},
		pluck="for_value",
	)
	if user_companies and doc.company not in user_companies:
		return False

	# Sales Engineer: must be the owner
	if "Sales Engineer" in roles and doc.sales_engineer == user:
		return True

	# Application Engineer: must be assigned
	if "Application Engineer" in roles:
		assigned_users = [row.user for row in doc.assignments if row.active]
		if user in assigned_users:
			return True

	# Manager roles: company-level access is sufficient
	manager_roles = {
		"Sales Manager",
		"Commercial Director",
		"General Manager",
		"Department Manager",
		"Inquiry Coordinator",
	}
	if manager_roles.intersection(roles):
		return True

	return False
