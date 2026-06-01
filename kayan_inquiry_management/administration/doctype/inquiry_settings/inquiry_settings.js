// Copyright (c) 2026, Kayan Automation and contributors
// For license information, please see license.txt

frappe.ui.form.on("Inquiry Settings", {
	refresh(frm) {
		frm.set_intro(
			__("Configure AI processing, SLA timers, notifications, escalation, and approval settings for the Inquiry Management system."),
			"blue"
		);
	},
});
