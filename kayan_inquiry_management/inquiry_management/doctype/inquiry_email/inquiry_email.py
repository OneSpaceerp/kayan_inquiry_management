# Copyright (c) 2026, Kayan Automation and contributors
from frappe.model.document import Document


class InquiryEmail(Document):
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		cc: DF.LongText | None
		direction: DF.Literal["Incoming", "Outgoing"]
		email_file: DF.Link | None
		email_from: DF.Data | None
		email_to: DF.LongText | None
		message_id: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		received_on: DF.Datetime | None
		subject: DF.Data | None
		thread_id: DF.Data | None

	pass
