# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

"""Add Opportunity.custom_inquiry_ticket so a deal points back at its inquiry.

The qualify flow opens a real Opportunity form rather than rebuilding Kayan's
mandatory commercial fields in a dialog. That means the Opportunity is saved by
the user, outside our code, so the link back to the Inquiry Ticket cannot be
written by the caller -- the ``on_update`` hook in hooks.py reads this field and
writes ``Inquiry Ticket.opportunity`` when the deal is saved.

Shipped as a patch rather than a fixture because fixtures are exported from a
site, not authored in an app: a new environment that has never had the field
would never receive it.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
	create_custom_field(
		"Opportunity",
		{
			"fieldname": "custom_inquiry_ticket",
			"label": "Inquiry Ticket",
			"fieldtype": "Link",
			"options": "Inquiry Ticket",
			"insert_after": "opportunity_from",
			"read_only": 1,
			"no_copy": 1,
			"description": (
				"The inquiry this Opportunity was qualified from. Set automatically "
				"when the deal is opened from an Inquiry Ticket."
			),
		},
	)
	frappe.db.commit()
