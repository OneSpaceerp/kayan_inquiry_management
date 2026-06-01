# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class InquiryLostReason(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		active: DF.Check
		reason_name: DF.Data
	# end: auto-generated types

	pass
