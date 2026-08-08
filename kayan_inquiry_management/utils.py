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
	"""Resolve the User who owns inquiries received at ``mailbox``.

	Resolution order:

	1. **Mailbox Mapping** — the override table. Use it for shared or functional
	   mailboxes (sales@, info@, tenders@) and for any case where the recipient
	   should not be the owner.
	2. **Direct User lookup** — ERPNext User IDs at Kayan *are* the email
	   addresses, so ``yousef.tharwat@kayan-eg.net`` is both the recipient and the
	   User id. This makes the common case a primary-key hit and removes the need
	   to pre-populate a mapping row for all ~35-40 staff mailboxes.

	Returns None when neither resolves, which the caller must treat as "route to
	review" rather than guessing an owner.
	"""
	if not mailbox:
		return None

	mailbox = mailbox.strip().lower()

	mapped = frappe.db.get_value(
		"Mailbox Mapping",
		{"mailbox": mailbox, "active": 1},
		"sales_engineer",
	)
	if mapped:
		return mapped

	if frappe.db.exists("User", {"name": mailbox, "enabled": 1}):
		return mailbox

	return None


def get_managers_for_user(user: str, company: str | None = None) -> list[dict]:
	"""Return the manager/escalation chain for ``user``, lowest level first.

	Order of precedence:

	1. Inquiry Assignment Rule scoped to the user AND company
	2. Inquiry Assignment Rule scoped to the user with no company
	3. The global escalation defaults in Inquiry Settings

	Returns an empty list if nothing resolves — callers should log that rather
	than silently proceeding with no escalation path.
	"""
	if not user:
		return []

	rule_name = None
	if company:
		rule_name = frappe.db.get_value(
			"Inquiry Assignment Rule", {"user": user, "company": company, "active": 1}, "name"
		)
	if not rule_name:
		rule_name = frappe.db.get_value(
			"Inquiry Assignment Rule", {"user": user, "company": ["in", ["", None]], "active": 1}, "name"
		)
	if not rule_name:
		rule_name = frappe.db.get_value("Inquiry Assignment Rule", {"user": user, "active": 1}, "name")

	if rule_name:
		rule = frappe.get_cached_doc("Inquiry Assignment Rule", rule_name)
		rows = sorted(rule.managers or [], key=lambda r: r.escalation_level or 0)
		return [
			{
				"manager": r.manager,
				"manager_role": r.manager_role,
				"escalation_level": r.escalation_level or 0,
				"notify_on_assignment": bool(r.notify_on_assignment),
				"source": "Inquiry Assignment Rule",
			}
			for r in rows
		]

	# Fall back to the org-wide defaults already configured in Inquiry Settings.
	settings = get_inquiry_settings()
	if not settings:
		return []

	defaults = [
		(settings.get("escalation_direct_manager"), "Direct Manager", 1),
		(settings.get("escalation_sales_manager"), "Sales Manager", 2),
		(settings.get("escalation_department_manager"), "Department Manager", 3),
	]
	return [
		{
			"manager": mgr,
			"manager_role": role,
			"escalation_level": level,
			"notify_on_assignment": False,
			"source": "Inquiry Settings",
		}
		for mgr, role, level in defaults
		if mgr and mgr != user
	]


def get_internal_domains() -> set[str]:
	"""Domains treated as internal to Kayan."""
	settings = get_inquiry_settings()
	raw = (settings.get("internal_domains") if settings else "") or "kayan-eg.net"
	return {d.strip().lower().lstrip("@") for d in raw.splitlines() if d.strip()}


def is_internal_address(email: str) -> bool:
	"""True when ``email`` belongs to a Kayan domain."""
	if not email or "@" not in email:
		return False
	return email.strip().lower().rsplit("@", 1)[-1] in get_internal_domains()


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


def calculate_sla_deadline(start_time, sla_hours: int, company: str | None = None):
	"""Calculate an SLA deadline from a start time plus a configurable duration.

	BUGFIX (review finding A7 / risk OR-02): ``Inquiry Settings.sla_business_hours_only``
	is enabled in production, but this function ignored it and did naive calendar
	arithmetic. That is why every existing Inquiry Ticket shows ``sla_status =
	"Breached"`` — a 4-hour assignment SLA started on a Thursday evening expires
	overnight, before anyone is at work.

	When the setting is on, only working hours on working days are counted, and
	Holiday List dates are skipped entirely.
	"""
	from datetime import timedelta

	settings = get_inquiry_settings()
	if not settings or not settings.get("sla_business_hours_only"):
		return start_time + timedelta(hours=sla_hours)

	return add_business_hours(start_time, sla_hours, company)


# Default working window, used when no Employee/Company schedule overrides it.
BUSINESS_DAY_START_HOUR = 9
BUSINESS_DAY_END_HOUR = 17
# Egypt: the working week runs Sunday-Thursday. Python weekday(): Mon=0 .. Sun=6.
NON_WORKING_WEEKDAYS = {4, 5}  # Friday, Saturday


def _get_holiday_dates(company: str | None = None) -> set:
	"""Return the set of holiday dates from the Company's default Holiday List."""
	holiday_list = None
	if company:
		holiday_list = frappe.db.get_value("Company", company, "default_holiday_list")
	if not holiday_list:
		holiday_list = frappe.db.get_single_value("HR Settings", "default_holiday_list")
	if not holiday_list:
		return set()

	rows = frappe.get_all(
		"Holiday",
		filters={"parent": holiday_list},
		pluck="holiday_date",
	)
	return set(rows or [])


def _is_working_day(dt, holidays: set) -> bool:
	return dt.weekday() not in NON_WORKING_WEEKDAYS and dt.date() not in holidays


def add_business_hours(start_time, sla_hours: int, company: str | None = None):
	"""Advance ``start_time`` by ``sla_hours`` of working time.

	Counts only BUSINESS_DAY_START_HOUR..BUSINESS_DAY_END_HOUR on working days,
	skipping weekends and Holiday List dates.
	"""
	from datetime import datetime, time, timedelta

	holidays = _get_holiday_dates(company)
	remaining = timedelta(hours=sla_hours or 0)
	cursor = start_time

	# If we start outside the working window, jump to the next window opening.
	def _window_for(day):
		return (
			datetime.combine(day.date(), time(BUSINESS_DAY_START_HOUR)),
			datetime.combine(day.date(), time(BUSINESS_DAY_END_HOUR)),
		)

	guard = 0
	while remaining > timedelta(0):
		guard += 1
		if guard > 3650:  # ~10 years of days; prevents an infinite loop on bad config
			frappe.log_error(
				message=f"SLA calculation exceeded iteration guard for start={start_time}, hours={sla_hours}",
				title="calculate_sla_deadline guard tripped",
			)
			return start_time + timedelta(hours=sla_hours)

		if not _is_working_day(cursor, holidays):
			cursor = datetime.combine((cursor + timedelta(days=1)).date(), time(BUSINESS_DAY_START_HOUR))
			continue

		day_start, day_end = _window_for(cursor)
		if cursor < day_start:
			cursor = day_start
		if cursor >= day_end:
			cursor = datetime.combine((cursor + timedelta(days=1)).date(), time(BUSINESS_DAY_START_HOUR))
			continue

		available = day_end - cursor
		if available >= remaining:
			return cursor + remaining

		remaining -= available
		cursor = datetime.combine((cursor + timedelta(days=1)).date(), time(BUSINESS_DAY_START_HOUR))

	return cursor


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
