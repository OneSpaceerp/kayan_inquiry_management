# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class InquiryAssignmentManager(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		escalation_level: DF.Int
		manager: DF.Link
		manager_role: DF.Literal["Direct Manager", "Sales Manager", "Department Manager", "Escalation Only"]
		notify_on_assignment: DF.Check
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
