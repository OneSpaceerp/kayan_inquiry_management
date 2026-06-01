# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class InquiryLineItem(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		application_engineer: DF.Link | None
		customer_item_code: DF.Data | None
		delivery_location: DF.Data | None
		item: DF.Link | None
		item_description: DF.Text
		line_no: DF.Int
		manually_corrected: DF.Check
		match_confidence: DF.Percent
		matched_by_ai: DF.Check
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		quantity: DF.Float
		requested_brand: DF.Data | None
		required_date: DF.Date | None
		uom: DF.Data | None
	# end: auto-generated types

	pass
