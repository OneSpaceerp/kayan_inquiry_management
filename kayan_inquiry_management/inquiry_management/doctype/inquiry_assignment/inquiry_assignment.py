# Copyright (c) 2026, Kayan Automation and contributors
from frappe.model.document import Document


class InquiryAssignment(Document):
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		active: DF.Check
		assigned_by: DF.Link | None
		assigned_on: DF.Datetime | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		role_type: DF.Literal["Application Engineer", "Reviewer", "Approver"]
		user: DF.Link

	pass
