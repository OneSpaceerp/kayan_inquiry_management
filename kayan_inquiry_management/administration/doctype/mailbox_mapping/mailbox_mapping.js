// Copyright (c) 2026, Kayan Automation and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mailbox Mapping", {
	refresh(frm) {
		// Filter sales_engineer to show only users with Sales Engineer role
		frm.set_query("sales_engineer", function () {
			return {
				query: "frappe.core.doctype.user.user.user_query",
				filters: { role: "Sales Engineer" },
			};
		});
	},
});
