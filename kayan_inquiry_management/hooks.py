app_name = "kayan_inquiry_management"
app_title = "Kayan Inquiry Management"
app_publisher = "Kayan Automation"
app_description = "AI-Powered Email Inquiry Management & Quotation Workflow for ERPNext v16"
app_email = "dev@kayan.com"
app_license = "gpl-3.0"
app_icon = "fa fa-envelope"

# Install ERPNext (and Frappe) before this app
required_apps = ["erpnext"]

# --------------------------------------------------------------------------
# Asset bundling (uncomment when JS/CSS bundles are created)
# --------------------------------------------------------------------------
# app_include_js = "kayan_inquiry_management.bundle.js"
# app_include_css = "kayan_inquiry_management.bundle.css"

# --------------------------------------------------------------------------
# Document events — react to events on custom and standard DocTypes
# --------------------------------------------------------------------------
# NOTE (review finding C-3): the "Inquiry Ticket" entry was removed here.
# Frappe already runs the InquiryTicket controller's own validate() and
# on_update(); registering hooks that called the same private methods made every
# status change process twice. The controller is now the single source of truth.
doc_events = {
	"Opportunity": {
		"validate": "kayan_inquiry_management.api.clean_opportunity_links",
	},
}

# --------------------------------------------------------------------------
# Scheduled jobs
# --------------------------------------------------------------------------
scheduler_events = {
	"hourly": [
		"kayan_inquiry_management.sla_management.sla_monitor.check_sla_breaches",
	],
}

# --------------------------------------------------------------------------
# Fixtures — shipped with the app, applied on bench migrate
# --------------------------------------------------------------------------
fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			[
				"module",
				"in",
				[
					"Inquiry Management",
					"AI Processing",
					"Technical Review",
					"Quotation Workspace",
					"Approval Management",
					"SLA Management",
					"Reporting",
					"Administration",
				],
			]
		],
	},
	{
		"dt": "Property Setter",
		"filters": [
			[
				"module",
				"in",
				[
					"Inquiry Management",
					"AI Processing",
					"Technical Review",
					"Quotation Workspace",
					"Approval Management",
					"SLA Management",
					"Reporting",
					"Administration",
				],
			]
		],
	},
	{
		"dt": "Role",
		"filters": [
			[
				"name",
				"in",
				[
					"Sales Engineer",
					"Application Engineer",
					"Inquiry Coordinator",
					"Sales Manager",
					"Commercial Director",
					"Department Manager",
					"General Manager",
				],
			]
		],
	},
]

# --------------------------------------------------------------------------
# Permissions — company-based filtering for custom DocTypes
# --------------------------------------------------------------------------
permission_query_conditions = {
	"Inquiry Ticket": "kayan_inquiry_management.permissions.inquiry_ticket_query_conditions",
}

has_permission = {
	"Inquiry Ticket": "kayan_inquiry_management.permissions.inquiry_ticket_has_permission",
}
