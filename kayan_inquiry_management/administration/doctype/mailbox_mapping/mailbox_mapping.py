# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class MailboxMapping(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		active: DF.Check
		company: DF.Link
		mailbox: DF.Data
		sales_engineer: DF.Link
	# end: auto-generated types

	def validate(self):
		"""Ensure mailbox is a valid email format and sales engineer has SE role."""
		if self.mailbox and "@" not in self.mailbox:
			frappe.throw(_("Mailbox must be a valid email address."))

		if self.sales_engineer:
			roles = frappe.get_roles(self.sales_engineer)
			if "Sales Engineer" not in roles and "System Manager" not in roles:
				frappe.throw(
					_("User {0} does not have the Sales Engineer role.").format(self.sales_engineer)
				)
