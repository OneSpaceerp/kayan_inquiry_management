# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from kayan_inquiry_management.utils import (
	VALID_TRANSITIONS,
	calculate_sla_deadline,
	create_audit_event,
	get_inquiry_settings,
	get_sales_engineer_for_mailbox,
	validate_status_transition,
)


class InquiryTicket(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from kayan_inquiry_management.approval_management.doctype.inquiry_approval.inquiry_approval import (
			InquiryApproval,
		)
		from kayan_inquiry_management.inquiry_management.doctype.inquiry_assignment.inquiry_assignment import (
			InquiryAssignment,
		)
		from kayan_inquiry_management.inquiry_management.doctype.inquiry_email.inquiry_email import (
			InquiryEmail,
		)
		from kayan_inquiry_management.inquiry_management.doctype.inquiry_line_item.inquiry_line_item import (
			InquiryLineItem,
		)
		from kayan_inquiry_management.inquiry_management.doctype.inquiry_revision.inquiry_revision import (
			InquiryRevision,
		)
		from kayan_inquiry_management.inquiry_management.doctype.inquiry_status_history.inquiry_status_history import (
			InquiryStatusHistory,
		)

		ai_classification: DF.Data | None
		ai_confidence: DF.Percent
		ai_extracted_data: DF.Code | None
		ai_needs_review: DF.Check
		ai_provider: DF.Data | None
		ai_summary: DF.Text | None
		amended_from: DF.Link | None
		approvals: DF.Table[InquiryApproval]
		assigned_date: DF.Datetime | None
		assignments: DF.Table[InquiryAssignment]
		cancellation_reason: DF.SmallText | None
		company: DF.Link
		company_name: DF.Data | None
		contact_email: DF.Data | None
		contact_first_name: DF.Data | None
		contact_last_name: DF.Data | None
		contact_person: DF.Data | None
		contact_phone: DF.Data | None
		currency: DF.Link | None
		current_quotation: DF.Link | None
		customer: DF.Link | None
		customer_match_method: DF.Literal["", "Company Name", "Email Domain", "Email Address", "Manual"]
		delivery_location: DF.Data | None
		due_date: DF.Date | None
		emails: DF.Table[InquiryEmail]
		estimated_value: DF.Currency
		inquiry_coordinator: DF.Link | None
		inquiry_type: DF.Literal["", "RFQ", "Quotation Request", "Tender", "Budget Request", "Commercial Inquiry", "RFP"]
		forwarding_mailbox: DF.Data | None
		lead: DF.Link | None
		line_items: DF.Table[InquiryLineItem]
		lost_reason: DF.Link | None
		message_id: DF.Data | None
		naming_series: DF.Literal["INQ-.YYYY.-.#####"]
		opportunity: DF.Link | None
		original_email_subject: DF.Data | None
		original_recipient: DF.Data | None
		original_recipients: DF.SmallText | None
		original_sent_date: DF.Datetime | None
		outcome_remarks: DF.Text | None
		priority: DF.Literal["Low", "Medium", "High", "Urgent"]
		quotation_count: DF.Int
		received_date: DF.Datetime | None
		recipient_resolution_method: DF.Literal[
			"",
			"Envelope-To",
			"Received-For",
			"Bcc",
			"To Header",
			"Cc Header",
			"Manual Forward Sender",
			"Unresolved",
		]
		responsible_manager: DF.Link | None
		revision_count: DF.Int
		revisions: DF.Table[InquiryRevision]
		sales_engineer: DF.Link | None
		sales_order: DF.Link | None
		sla_assignment_deadline: DF.Datetime | None
		sla_quotation_deadline: DF.Datetime | None
		sla_status: DF.Literal["Not Started", "Active", "Met", "Breached", "Escalated"]
		sla_technical_deadline: DF.Datetime | None
		source_mailbox: DF.Data | None
		status: DF.Literal[
			"New",
			"Pending Review",
			"Assigned to Sales Engineer",
			"Assigned to Application Engineer",
			"Technical Review In Progress",
			"Quotation Preparation In Progress",
			"Pending Approval",
			"Approved",
			"Quotation Sent",
			"Customer Follow-Up",
			"Revision Requested",
			"Won",
			"Lost",
			"Cancelled",
		]
		status_history: DF.Table[InquiryStatusHistory]
		tender_number: DF.Data | None
	# end: auto-generated types

	def before_insert(self):
		"""Set defaults on new inquiry creation."""
		if not self.status:
			self.status = "New"
		if not self.sla_status:
			self.sla_status = "Not Started"
		if not self.received_date:
			self.received_date = frappe.utils.now_datetime()

		# Auto-assign Sales Engineer from mailbox mapping
		if self.source_mailbox and not self.sales_engineer:
			se = get_sales_engineer_for_mailbox(self.source_mailbox)
			if se:
				self.sales_engineer = se

		# Start SLA timer
		self._start_assignment_sla()

	def validate(self):
		"""Run all validation before save.

		BUGFIX (review finding C-1): the previous status must be captured *here*,
		while the database still holds the old value. ``on_update()`` runs after the
		write, so ``get_db_value("status")`` there always returned the NEW status,
		making every downstream comparison a no-op. The consequences were silent:
		no status history rows, no status-change audit events, technical and
		quotation SLA deadlines never set, and ``sla_status`` never reaching "Met".
		"""
		self._previous_status = None if self.is_new() else self.get_db_value("status")

		self._validate_status_transition()
		self._validate_outcome_fields()
		self._validate_assignments()
		self._validate_approval_chain()

		# BUGFIX (review finding C-2): append the history row during validate so the
		# normal save cycle persists it. The old code appended in on_update() and
		# called db_update(), which writes parent columns only — the child row was
		# silently discarded and never reached `tabInquiry Status History`.
		if self._previous_status and self._previous_status != self.status:
			self.append(
				"status_history",
				{
					"old_status": self._previous_status,
					"new_status": self.status,
					"changed_by": frappe.session.user,
					"changed_on": frappe.utils.now_datetime(),
				},
			)

	def on_update(self):
		"""After save — write the audit trail and advance SLA timers."""
		previous_status = getattr(self, "_previous_status", None)
		if not previous_status or previous_status == self.status:
			return

		create_audit_event(
			entity_type="Inquiry Ticket",
			entity_id=self.name,
			action=f"Status Changed: {previous_status} → {self.status}",
			details=f"Status changed from '{previous_status}' to '{self.status}' by {frappe.session.user}",
		)
		self._update_sla_on_transition(previous_status)

	def _validate_status_transition(self):
		"""Enforce valid status transitions per the workflow specification."""
		if self.is_new():
			return

		old_status = self.get_db_value("status")
		if old_status and old_status != self.status:
			if not validate_status_transition(old_status, self.status):
				allowed = ", ".join(VALID_TRANSITIONS.get(old_status, []))
				frappe.throw(
					_("Cannot change status from {0} to {1}. Allowed transitions: {2}").format(
						old_status, self.status, allowed or "None (terminal state)"
					)
				)

	def _validate_outcome_fields(self):
		"""Ensure Lost/Cancelled have required reason fields."""
		if self.status == "Lost" and not self.lost_reason:
			frappe.throw(_("Lost Reason is required when marking an inquiry as Lost."))

		if self.status == "Cancelled" and not self.cancellation_reason:
			frappe.throw(_("Cancellation Reason is required when cancelling an inquiry."))

	def _validate_approval_chain(self):
		"""Refuse to reach Approved without a completed approval chain.

		SECURITY (review finding S-7 / risk SR-04): the approval chain lived
		entirely in n8n workflow 06. Because ``VALID_TRANSITIONS`` permits
		Pending Approval → Approved, anyone with write access could set the status
		directly and self-approve. Nothing server-side stopped it.

		Enforcement rules:
		  * at least one Inquiry Approval row must carry decision "Approved"
		  * no row may still be awaiting a decision
		  * no row may carry decision "Rejected"

		NOTE: value-based thresholds (FR-21) are not enforced yet — Inquiry Settings
		defines approval_level_1..4_role but has no threshold amount fields. Those
		arrive with Workstream B3, after which this method should additionally
		require an Approved row for every level triggered by estimated_value.
		"""
		previous_status = getattr(self, "_previous_status", None)
		if previous_status != "Pending Approval" or self.status != "Approved":
			return

		approvals = list(self.approvals or [])
		if not approvals:
			frappe.throw(
				_("Cannot approve {0}: no approval records exist. The approval chain must be completed first.").format(
					self.name
				)
			)

		rejected = [a for a in approvals if a.decision == "Rejected"]
		if rejected:
			levels = ", ".join(str(a.level) for a in rejected)
			frappe.throw(_("Cannot approve: approval was rejected at level {0}.").format(levels))

		pending = [a for a in approvals if not a.decision or a.decision not in ("Approved", "Rejected")]
		if pending:
			levels = ", ".join(str(a.level) for a in pending)
			frappe.throw(_("Cannot approve: approval is still outstanding at level {0}.").format(levels))

		if not any(a.decision == "Approved" for a in approvals):
			frappe.throw(_("Cannot approve: no level has been approved."))

	def _validate_assignments(self):
		"""Ensure at least one active assignment when status requires it."""
		if self.status in [
			"Assigned to Application Engineer",
			"Technical Review In Progress",
			"Quotation Preparation In Progress",
		]:
			active_assignments = [a for a in self.assignments if a.active]
			if not active_assignments:
				frappe.throw(
					_("At least one active Application Engineer assignment is required for status: {0}").format(
						self.status
					)
				)

	def _start_assignment_sla(self):
		"""Start the assignment SLA timer on new inquiry creation."""
		settings = get_inquiry_settings()
		if settings and settings.assignment_sla_hours:
			now = frappe.utils.now_datetime()
			# Pass the company: calculate_sla_deadline resolves the Holiday List from
			# it, and without it no holiday is ever skipped -- deadlines silently
			# counted Eid and national holidays as working days.
			self.sla_assignment_deadline = calculate_sla_deadline(
				now, settings.assignment_sla_hours, self.company
			)
			self.sla_status = "Active"

	def _update_sla_on_transition(self, previous_status: str | None = None):
		"""Start/stop SLA timers based on status transitions.

		``previous_status`` is passed in from ``on_update()`` (captured during
		validate). It must NOT be re-read from the database here — see C-1.
		"""
		if self.is_new() or not previous_status or previous_status == self.status:
			return

		settings = get_inquiry_settings()
		if not settings:
			return

		now = frappe.utils.now_datetime()

		# Start technical SLA when assigned to Application Engineer
		if self.status == "Assigned to Application Engineer" and settings.technical_sla_hours:
			self.db_set(
				"sla_technical_deadline",
				calculate_sla_deadline(now, settings.technical_sla_hours, self.company),
				update_modified=False,
			)

		# Start quotation SLA when entering quotation preparation
		if self.status == "Quotation Preparation In Progress" and settings.quotation_sla_hours:
			self.db_set(
				"sla_quotation_deadline",
				calculate_sla_deadline(now, settings.quotation_sla_hours, self.company),
				update_modified=False,
			)

		# Mark SLA as met on terminal positive states
		if self.status in ["Won", "Approved", "Quotation Sent"]:
			if self.sla_status in ["Active", "Not Started"]:
				self.db_set("sla_status", "Met", update_modified=False)

	# ------------------------------------------------------------------
	# Public API methods (called from api.py or client-side)
	# ------------------------------------------------------------------

	def change_status(self, new_status: str, remarks: str = ""):
		"""Change status with validation and audit trail."""
		old_status = self.status
		self.status = new_status
		self.save()
		return {"old_status": old_status, "new_status": new_status}

	def assign_engineer(self, user: str, role_type: str = "Application Engineer"):
		"""Add an engineer assignment to this inquiry."""
		self.append(
			"assignments",
			{
				"user": user,
				"role_type": role_type,
				"assigned_by": frappe.session.user,
				"assigned_on": frappe.utils.now_datetime(),
				"active": 1,
			},
		)
		self.assigned_date = frappe.utils.now_datetime()
		self.save()

		create_audit_event(
			entity_type="Inquiry Ticket",
			entity_id=self.name,
			action=f"Engineer Assigned: {user}",
			details=f"{role_type} '{user}' assigned by {frappe.session.user}",
		)


# ------------------------------------------------------------------
# NOTE (review finding C-3): the previous `validate_transition` and
# `on_update_audit` wrappers were registered in hooks.py doc_events AND
# duplicated logic the controller's own validate()/on_update() already ran.
# Frappe executes both the controller method and the hook, so everything fired
# twice. That was harmless only while C-1 made the on_update path a no-op; with
# C-1 fixed it would have produced duplicate history rows and audit events.
# The doc_events entry for "Inquiry Ticket" has been removed from hooks.py and
# these wrappers deleted. Controller methods are the single source of truth.
# ------------------------------------------------------------------
