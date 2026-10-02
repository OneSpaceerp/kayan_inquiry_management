// Copyright (c) 2026, Kayan Automation and contributors
// For license information, please see license.txt

frappe.ui.form.on("Inquiry Ticket", {
	refresh(frm) {
		// ---- Indicator colors per status ----
		frm.page.set_indicator(get_status_indicator(frm.doc.status));

		// ---- Status action buttons ----
		if (!frm.is_new()) {
			add_qualify_button(frm);
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

// ---- Helper: read a field out of the AI extraction blob ----
// ai_extracted_data is Long Text holding the extractor's JSON. It is model
// output, so treat it as untrusted: never assume it parses, and never assume a
// key is present.
function extracted(frm, key) {
	try {
		const data = JSON.parse(frm.doc.ai_extracted_data || "{}");
		const value = data[key];
		return typeof value === "string" ? value.trim() : "";
	} catch (e) {
		return "";
	}
}

// ---- Helper: Qualify Inquiry ----
// Intake links only what it could match exactly. This is where a human decides
// what the customer and project actually are, and the Opportunity is opened
// from a real form rather than built in code — Kayan's Opportunity carries
// mandatory commercial fields (contractor, consultant, owner/end user, project
// sector, scope of supply) that are customised on the site, and rebuilding them
// here would duplicate validation this app does not own.
function add_qualify_button(frm) {
	if (frm.doc.opportunity) {
		frm.add_custom_button(__("View Opportunity"), function () {
			frappe.set_route("Form", "Opportunity", frm.doc.opportunity);
		});
		return;
	}

	frm.add_custom_button(__("Qualify Inquiry"), function () {
		open_qualify_dialog(frm);
	}).addClass("btn-primary");
}

function open_qualify_dialog(frm) {
	const has_customer = Boolean(frm.doc.customer);

	const dialog = new frappe.ui.Dialog({
		title: __("Qualify Inquiry"),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				options:
					`<p class="text-muted small">${__(
						"Intake linked only records that already existed. Confirm the customer and project below — anything you create here is created from these values, not from the AI extraction."
					)}</p>`,
			},

			{ fieldtype: "Section Break", label: __("Customer") },
			{
				fieldname: "customer",
				fieldtype: "Link",
				options: "Customer",
				label: __("Customer"),
				default: frm.doc.customer || "",
				depends_on: "eval:!doc.create_lead",
			},
			{
				fieldname: "lead",
				fieldtype: "Link",
				options: "Lead",
				label: __("Existing Lead"),
				default: frm.doc.lead || "",
				depends_on: "eval:!doc.create_lead && !doc.customer",
			},
			{
				fieldname: "create_lead",
				fieldtype: "Check",
				label: __("This is a new customer — create a Lead"),
				default: 0,
				read_only: has_customer ? 1 : 0,
				description: has_customer
					? __("Already linked to a Customer, so a Lead would duplicate it.")
					: "",
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "lead_name",
				fieldtype: "Data",
				label: __("Contact Name"),
				depends_on: "eval:doc.create_lead",
				default: frm.doc.contact_person || "",
			},
			{
				fieldname: "lead_company",
				fieldtype: "Data",
				label: __("Company Name"),
				depends_on: "eval:doc.create_lead",
				default: frm.doc.company_name || extracted(frm, "company_name"),
			},
			{
				fieldname: "lead_email",
				fieldtype: "Data",
				options: "Email",
				label: __("Email"),
				depends_on: "eval:doc.create_lead",
				default: frm.doc.contact_email || "",
			},
			{
				fieldname: "lead_phone",
				fieldtype: "Data",
				label: __("Phone"),
				depends_on: "eval:doc.create_lead",
				default: frm.doc.contact_phone || "",
			},

			{ fieldtype: "Section Break", label: __("Project") },
			{
				fieldname: "project",
				fieldtype: "Link",
				options: "Project",
				label: __("Existing Project"),
				default: frm.doc.project || "",
				depends_on: "eval:!doc.create_project",
			},
			{
				fieldname: "create_project",
				fieldtype: "Check",
				label: __("This is a new project — create it"),
				default: 0,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "new_project_name",
				fieldtype: "Data",
				label: __("New Project Name"),
				depends_on: "eval:doc.create_project",
				default: extracted(frm, "project_name") || frm.doc.delivery_location || "",
				description: __(
					"Checked against existing projects first — a name that already matches will link to that project instead of creating a second one."
				),
			},
		],
		primary_action_label: __("Qualify"),
		primary_action(values) {
			if (!values.customer && !values.lead && !values.create_lead) {
				frappe.msgprint({
					title: __("Customer required"),
					message: __("Pick a Customer or an existing Lead, or tick the box to create a new Lead."),
					indicator: "orange",
				});
				return;
			}

			frappe.call({
				method: "kayan_inquiry_management.intake.qualify_inquiry",
				args: Object.assign({ ticket: frm.doc.name }, values),
				freeze: true,
				freeze_message: __("Qualifying inquiry..."),
				callback(r) {
					if (!r.message) {
						return;
					}
					dialog.hide();
					frm.reload_doc();
					offer_opportunity(r.message);
				},
			});
		},
	});

	dialog.show();
}

// Hands the user a prefilled Opportunity form. frappe.route_options is the
// stable way to seed a new doc across Frappe versions — the form then renders
// and validates Kayan's own custom fields, which is the whole point of not
// creating the Opportunity server-side.
function offer_opportunity(result) {
	const prefill = result.opportunity || {};
	if (!prefill.party_name) {
		frappe.show_alert({ message: __("Inquiry qualified."), indicator: "green" });
		return;
	}

	frappe.confirm(
		__("Inquiry qualified. Create the Opportunity now?"),
		function () {
			frappe.route_options = Object.fromEntries(
				Object.entries(prefill).filter(([, v]) => v !== null && v !== undefined && v !== "")
			);
			frappe.new_doc("Opportunity");
		},
		function () {
			frappe.show_alert({
				message: __("Qualified. Use Qualify Inquiry again when you are ready for the Opportunity."),
				indicator: "blue",
			});
		}
	);
}

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
