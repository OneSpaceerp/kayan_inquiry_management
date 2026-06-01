# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class InquirySettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		ai_api_key: DF.Password | None
		ai_api_url: DF.Data | None
		approval_level_1_role: DF.Link | None
		approval_level_2_role: DF.Link | None
		approval_level_3_role: DF.Link | None
		approval_level_4_role: DF.Link | None
		assignment_sla_hours: DF.Int
		confidence_threshold: DF.Percent
		default_ai_provider: DF.Literal["", "OpenAI", "Gemini", "Claude", "Local"]
		email_notifications_enabled: DF.Check
		erp_notifications_enabled: DF.Check
		escalation_department_manager: DF.Link | None
		escalation_direct_manager: DF.Link | None
		escalation_sales_manager: DF.Link | None
		preferred_language: DF.Literal["English", "Arabic"]
		quotation_sla_hours: DF.Int
		sla_business_hours_only: DF.Check
		technical_sla_hours: DF.Int
	# end: auto-generated types

	def validate(self):
		"""Validate SLA values and confidence threshold."""
		if self.confidence_threshold and (self.confidence_threshold < 0 or self.confidence_threshold > 100):
			frappe.throw(frappe._("Confidence Threshold must be between 0 and 100."))

		if self.assignment_sla_hours and self.assignment_sla_hours < 1:
			frappe.throw(frappe._("Assignment SLA must be at least 1 hour."))

		if self.technical_sla_hours and self.technical_sla_hours < 1:
			frappe.throw(frappe._("Technical Review SLA must be at least 1 hour."))

		if self.quotation_sla_hours and self.quotation_sla_hours < 1:
			frappe.throw(frappe._("Quotation Preparation SLA must be at least 1 hour."))
