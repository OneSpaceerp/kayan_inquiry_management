# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class InquiryAssignmentRule(Document):
	"""Maps an inquiry-owning User to one or more managers.

	This is the authoritative source for manager resolution. It is seeded once
	from ``Employee.reports_to`` by a bootstrap patch, then maintained here.

	It is deliberately NOT a runtime read of the HR hierarchy. The live Employee
	data contains defects that would cause silent failures: one hierarchy root
	(``Ahmed Mohamed Mwafi``) has no ``user_id`` despite an enabled User existing,
	three records carry wrong-domain ``user_id`` values, one has an empty-string
	``reports_to``, and seven active employees have no user link at all.
	"""

	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from kayan_inquiry_management.administration.doctype.inquiry_assignment_manager.inquiry_assignment_manager import (
			InquiryAssignmentManager,
		)

		active: DF.Check
		company: DF.Link | None
		employee: DF.Link | None
		managers: DF.Table[InquiryAssignmentManager]
		priority: DF.Int
		user: DF.Link
	# end: auto-generated types

	def validate(self):
		self._validate_no_self_management()
		self._validate_unique_managers()
		self._validate_escalation_levels()

	def _validate_no_self_management(self):
		"""A user cannot be their own manager — that would loop escalation."""
		for row in self.managers or []:
			if row.manager == self.user:
				frappe.throw(
					_("Row {0}: {1} cannot be their own manager.").format(row.idx, self.user)
				)

	def _validate_unique_managers(self):
		"""Reject the same manager listed twice."""
		seen = set()
		for row in self.managers or []:
			if row.manager in seen:
				frappe.throw(_("Row {0}: {1} is listed more than once.").format(row.idx, row.manager))
			seen.add(row.manager)

	def _validate_escalation_levels(self):
		"""Escalation levels must be distinct so the chain has a defined order."""
		levels = [row.escalation_level for row in self.managers or [] if row.escalation_level]
		if len(levels) != len(set(levels)):
			frappe.throw(_("Escalation levels must be unique within a rule."))
