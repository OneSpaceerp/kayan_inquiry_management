# Copyright (c) 2026, Kayan Automation and contributors
from frappe.model.document import Document


class AIProcessingLog(Document):
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		execution_time: DF.Float
		input_tokens: DF.Int
		inquiry_ticket: DF.Link | None
		model: DF.Data | None
		output_tokens: DF.Int
		provider: DF.Data | None
		status: DF.Literal["Queued", "Processing", "Completed", "Failed"]
		task_type: DF.Data | None

	pass
