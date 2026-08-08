# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

"""Backfill the new email-intake fields on existing Inquiry Tickets.

Existing tickets predate centralised intake. Where ``source_mailbox`` already
holds a real address it is copied to ``original_recipient`` so historical rows
read consistently with new ones; where it holds the funnel address (or nothing)
the resolution method is marked ``Unresolved`` rather than inventing a value.

Live data at the time of writing: of 9 tickets, one carries the funnel address
``inquiries-inbox@kayan-eg.net``, one carries a real recipient that was never in
Mailbox Mapping, and the rest are NULL or empty.
"""

import frappe


def execute():
	if not frappe.db.has_column("Inquiry Ticket", "original_recipient"):
		return

	settings_mailbox = (
		frappe.db.get_single_value("Inquiry Settings", "forwarding_mailbox")
		or "inquiries-inbox@kayan-eg.net"
	)

	tickets = frappe.get_all(
		"Inquiry Ticket",
		fields=["name", "source_mailbox", "received_date"],
	)

	resolved, unresolved = 0, 0

	for t in tickets:
		mailbox = (t.source_mailbox or "").strip().lower()

		if mailbox and mailbox != settings_mailbox.strip().lower():
			# A real recipient was captured — treat it as the original.
			frappe.db.set_value(
				"Inquiry Ticket",
				t.name,
				{
					"original_recipient": mailbox,
					"original_recipients": mailbox,
					"recipient_resolution_method": "Envelope-To",
					"forwarding_mailbox": settings_mailbox,
					"original_sent_date": t.received_date,
				},
				update_modified=False,
			)
			resolved += 1
		else:
			frappe.db.set_value(
				"Inquiry Ticket",
				t.name,
				{
					"recipient_resolution_method": "Unresolved",
					"forwarding_mailbox": settings_mailbox,
					"original_sent_date": t.received_date,
				},
				update_modified=False,
			)
			unresolved += 1

	print(f"Intake backfill: {resolved} with a real recipient, {unresolved} marked Unresolved.")
