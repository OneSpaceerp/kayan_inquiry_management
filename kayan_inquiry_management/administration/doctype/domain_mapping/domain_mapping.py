# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class DomainMapping(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		active: DF.Check
		company: DF.Link
		email_domain: DF.Data
	# end: auto-generated types

	pass
