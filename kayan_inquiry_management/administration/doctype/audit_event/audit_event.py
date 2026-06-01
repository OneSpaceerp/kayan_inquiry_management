# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AuditEvent(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		action: DF.Data
		details: DF.LongText | None
		entity_id: DF.Data
		entity_type: DF.Data
		performed_by: DF.Data
		performed_on: DF.Datetime
	# end: auto-generated types

	def before_save(self):
		"""Prevent modification of audit records after initial creation."""
		if not self.is_new():
			frappe.throw(_("Audit Event records cannot be modified after creation."))

	def on_trash(self):
		"""Prevent deletion of audit records."""
		frappe.throw(_("Audit Event records cannot be deleted."))
