# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

"""One-time bootstrap of Inquiry Assignment Rule from the HR hierarchy.

Walks ``Employee.reports_to``, resolving ``user_id`` on both the employee and
their manager, and creates one Inquiry Assignment Rule per resolvable pair.

This runs ONCE. Inquiry Assignment Rule is authoritative afterwards and is never
re-synced from Employee — the live HR data contains defects that would cause
silent manager-resolution failures if read at runtime:

  * ``Ahmed Mohamed Mwafi`` has user_id = NULL although ahmed.mowafy@kayan-eg.net
    is an enabled User. Two employees report to him, so that branch dead-ends.
  * Three records carry wrong-domain user_ids (``@kayan.com``, ``@kayan-eg.com``)
    that match no User; one of them is still Active.
  * One record has ``reports_to = ""`` rather than NULL.
  * Seven Active employees have no user_id at all.

Every skip is logged so the gaps can be completed by hand rather than silently
inherited.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Inquiry Assignment Rule"):
		return

	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "user_id", "reports_to", "company"],
	)

	# Employee name -> user_id, for resolving the manager side of the link.
	manager_user = {
		e.name: e.user_id
		for e in frappe.get_all("Employee", fields=["name", "user_id"])
	}

	created, skipped = 0, []

	for emp in employees:
		if not emp.user_id:
			skipped.append((emp.name, "employee has no user_id"))
			continue

		# Empty string is a real value in this data set, not just NULL.
		if not (emp.reports_to or "").strip():
			skipped.append((emp.name, "no reports_to"))
			continue

		mgr_user = manager_user.get(emp.reports_to)
		if not mgr_user:
			skipped.append((emp.name, f"manager '{emp.reports_to}' has no user_id"))
			continue

		if not frappe.db.exists("User", emp.user_id):
			skipped.append((emp.name, f"user_id '{emp.user_id}' is not a User"))
			continue

		if not frappe.db.exists("User", mgr_user):
			skipped.append((emp.name, f"manager user '{mgr_user}' is not a User"))
			continue

		if emp.user_id == mgr_user:
			skipped.append((emp.name, "employee reports to themselves"))
			continue

		if frappe.db.exists("Inquiry Assignment Rule", emp.user_id):
			continue

		try:
			frappe.get_doc(
				{
					"doctype": "Inquiry Assignment Rule",
					"user": emp.user_id,
					"employee": emp.name,
					"company": emp.company,
					"active": 1,
					"priority": 10,
					"managers": [
						{
							"manager": mgr_user,
							"manager_role": "Direct Manager",
							"escalation_level": 1,
							"notify_on_assignment": 0,
						}
					],
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as exc:
			skipped.append((emp.name, f"insert failed: {exc}"))

	summary = [f"Inquiry Assignment Rule bootstrap: created {created}, skipped {len(skipped)}."]
	if skipped:
		summary.append("")
		summary.append("Skipped (complete these manually in Inquiry Assignment Rule):")
		summary.extend(f"  - {name}: {reason}" for name, reason in skipped)

	report = "\n".join(summary)
	print(report)
	frappe.log_error(message=report, title="Inquiry Assignment Rule bootstrap")
