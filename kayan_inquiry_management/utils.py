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
