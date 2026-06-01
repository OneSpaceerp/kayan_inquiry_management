// Copyright (c) 2026, Kayan Automation and contributors
// For license information, please see license.txt

frappe.ui.form.on("Inquiry Ticket", {
	refresh(frm) {
		// ---- Indicator colors per status ----
		frm.page.set_indicator(get_status_indicator(frm.doc.status));

		// ---- Status action buttons ----
		if (!frm.is_new()) {
			add_status_buttons(frm);
		}

		// ---- Link filters ----
		frm.set_query("sales_engineer", function () {
			return {
				query: "frappe.core.doctype.user.user.user_query",
				filters: { role: "Sales Engineer" },
			};
		});

		frm.set_query("inquiry_coordinator", function () {
			return {
				query: "frappe.core.doctype.user.user.user_query",
				filters: { role: "Inquiry Coordinator" },
			};
		});

		frm.set_query("lost_reason", function () {
			return { filters: { active: 1 } };
		});

		// ---- Sidebar links ----
		if (frm.doc.current_quotation) {
			frm.sidebar.add_user_action(__("View Quotation"), function () {
				frappe.set_route("Form", "Quotation", frm.doc.current_quotation);
			});
		}
		if (frm.doc.sales_order) {
			frm.sidebar.add_user_action(__("View Sales Order"), function () {
				frappe.set_route("Form", "Sales Order", frm.doc.sales_order);
			});
		}
	},

	status(frm) {
		// Show/hide outcome section based on status
		frm.toggle_display("outcome_section",
			["Won", "Lost", "Cancelled"].includes(frm.doc.status)
		);
	},

	onload(frm) {
		// Initial visibility toggle
		frm.trigger("status");
	},
});

// ---- Assignment child table events ----
frappe.ui.form.on("Inquiry Assignment", {
	user(frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		if (row.user && !row.assigned_by) {
			frappe.model.set_value(cdt, cdn, "assigned_by", frappe.session.user);
			frappe.model.set_value(cdt, cdn, "assigned_on", frappe.datetime.now_datetime());
		}
	},
});

// ---- Helper: Status indicator mapping ----
function get_status_indicator(status) {
	const map = {
		"New": "blue",
		"Pending Review": "orange",
		"Assigned to Sales Engineer": "blue",
		"Assigned to Application Engineer": "blue",
		"Technical Review In Progress": "yellow",
		"Quotation Preparation In Progress": "yellow",
		"Pending Approval": "orange",
		"Approved": "green",
		"Quotation Sent": "purple",
		"Customer Follow-Up": "purple",
		"Revision Requested": "orange",
		"Won": "green",
		"Lost": "red",
		"Cancelled": "grey",
	};
	return map[status] || "blue";
}

// ---- Helper: Context-sensitive action buttons ----
function add_status_buttons(frm) {
	const status = frm.doc.status;

	// Transition map: current status → allowed next statuses
	const transitions = {
		"New": ["Pending Review"],
		"Pending Review": ["Assigned to Sales Engineer"],
		"Assigned to Sales Engineer": ["Assigned to Application Engineer"],
		"Assigned to Application Engineer": ["Technical Review In Progress"],
		"Technical Review In Progress": ["Quotation Preparation In Progress"],
		"Quotation Preparation In Progress": ["Pending Approval"],
		"Pending Approval": ["Approved", "Quotation Preparation In Progress"],
		"Approved": ["Quotation Sent"],
		"Quotation Sent": ["Customer Follow-Up"],
		"Customer Follow-Up": ["Won", "Lost", "Revision Requested"],
		"Revision Requested": ["Technical Review In Progress", "Quotation Preparation In Progress"],
	};

	const allowed = transitions[status] || [];
	allowed.forEach(function (next_status) {
		frm.add_custom_button(
			__(next_status),
			function () {
				frappe.confirm(
					__("Change status to <b>{0}</b>?", [next_status]),
					function () {
						frm.set_value("status", next_status);
						frm.save();
					}
				);
			},
			__("Change Status")
		);
	});

	// Cancel button (available from most non-terminal states)
	const cancellable = [
		"Assigned to Sales Engineer",
		"Assigned to Application Engineer",
		"Technical Review In Progress",
		"Quotation Preparation In Progress",
		"Pending Approval",
		"Approved",
		"Quotation Sent",
		"Customer Follow-Up",
		"Revision Requested",
	];
	if (cancellable.includes(status)) {
		frm.add_custom_button(
			__("Cancel Inquiry"),
			function () {
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Cancellation Reason"), reqd: 1 },
					function (values) {
						frm.set_value("cancellation_reason", values.reason);
						frm.set_value("status", "Cancelled");
						frm.save();
					},
					__("Cancel Inquiry"),
					__("Confirm")
				);
			},
			__("Actions")
		);
	}

	// Create Quotation button (only when Approved)
	if (status === "Approved") {
		frm.add_custom_button(
			__("Create ERPNext Quotation"),
			function () {
				frappe.call({
					method: "kayan_inquiry_management.api.create_erpnext_quotation",
					args: { inquiry_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Creating quotation..."),
					callback: function (r) {
						if (r.message) {
							frappe.set_route("Form", "Quotation", r.message);
						}
					},
				});
			},
			__("Actions")
		);
	}

	// Request Revision button (during Customer Follow-Up)
	if (status === "Customer Follow-Up") {
		frm.add_custom_button(
			__("Request Revision"),
			function () {
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Text", label: __("Revision Reason"), reqd: 1 },
					function (values) {
						frappe.call({
							method: "kayan_inquiry_management.api.create_revision",
							args: { inquiry_name: frm.doc.name, reason: values.reason },
							freeze: true,
							callback: function () {
								frm.set_value("status", "Revision Requested");
								frm.save();
							},
						});
					},
					__("Request Revision"),
					__("Submit")
				);
			},
			__("Actions")
		);
	}
}
