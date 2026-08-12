# Copyright (c) 2026, Kayan Automation and contributors
# For license information, please see license.txt

"""Centralised email intake.

All company mailboxes auto-forward to a single address. This module turns one
forwarded email into (at most) one Inquiry Ticket, with the customer matched,
an Opportunity linked, an owner assigned from the *original* recipient, and the
manager chain resolved.

Why a single endpoint
---------------------
The previous design had n8n make eight sequential HTTP calls to build one
ticket: search customer, create opportunity, search lead, create lead, create
opportunity, create ticket, upload files, notify. That chain had no transaction
and no idempotency, so a failure at call six left an orphan Lead and Opportunity
with no ticket. The ``ignore_permissions`` / ``ignore_mandatory`` /
``frappe.db.commit()`` cluster in the old helpers existed to paper over exactly
that fragility.

One deliberate ``ignore_mandatory`` survives, in ``_ensure_opportunity``, and it
is not the same thing: Kayan's Opportunity carries mandatory fields (contractor,
consultant, owner/end user, project sector, scope of supply) that describe a
qualified deal, and no inbound RFQ contains them. That flag encodes a domain
fact — the record is completed by a human at qualification — rather than hiding
a transactional defect. Do not remove it without also giving intake a source for
those values.

Centralised intake also makes duplicates *structural* rather than incidental: a
customer who BCCs three Kayan engineers on one RFQ generates three forwarded
copies sharing a Message-ID. Deduplication therefore cannot be a best-effort
pre-flight check — it has to happen inside the same transaction as creation, or
concurrent n8n executions will race and create three tickets.
"""

import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import frappe
from frappe import _
from frappe.utils import get_datetime

from kayan_inquiry_management.utils import (
	create_audit_event,
	get_inquiry_settings,
	get_managers_for_user,
	get_sales_engineer_for_mailbox,
	is_internal_address,
)


# ----------------------------------------------------------------------------
# Recipient resolution
# ----------------------------------------------------------------------------

# Ordered by trustworthiness. Envelope-to is written by Kayan's own receiving
# Exim server, so it is present and correct on every server-forwarded message.
RESOLUTION_ORDER = (
	"Envelope-To",
	"Received-For",
	"Bcc",
	"To Header",
	"Cc Header",
	"Manual Forward Sender",
)


def _normalise(addr: str | None) -> str:
	return (addr or "").strip().lower()


def resolve_original_recipient(headers: dict) -> dict:
	"""Work out which Kayan address the customer actually wrote to.

	``headers`` carries pre-parsed address lists from the automation layer:
	``envelope_to``, ``received_for``, ``bcc``, ``to``, ``cc``, ``from_email``.

	NEVER consult ``Delivered-To``. On this mail system it is written once, by
	the final delivery hop, and always contains the central intake mailbox — so
	it looks like a valid Kayan address while being the same wrong answer every
	time. That failure mode presents as a mapping problem rather than a header
	problem, which is what makes it dangerous.

	Returns ``{recipient, recipients, method}``.
	"""
	settings = get_inquiry_settings()
	funnel = _normalise(settings.get("forwarding_mailbox") if settings else None) or (
		"inquiries-inbox@kayan-eg.net"
	)

	def kayan_only(values):
		out = []
		for v in values or []:
			v = _normalise(v)
			if v and v != funnel and is_internal_address(v) and v not in out:
				out.append(v)
		return out

	candidates = {
		"Envelope-To": kayan_only(headers.get("envelope_to")),
		"Received-For": kayan_only(headers.get("received_for")),
		"Bcc": kayan_only(headers.get("bcc")),
		"To Header": kayan_only(headers.get("to")),
		"Cc Header": kayan_only(headers.get("cc")),
	}

	# A staff member forwarding a customer email by hand: the envelope points at
	# the funnel, so the forwarding employee is the owner.
	sender = _normalise(headers.get("from_email"))
	if is_internal_address(sender) and sender != funnel:
		candidates["Manual Forward Sender"] = [sender]

	all_recipients = []
	for key in RESOLUTION_ORDER:
		for addr in candidates.get(key, []):
			if addr not in all_recipients:
				all_recipients.append(addr)

	for method in RESOLUTION_ORDER:
		found = candidates.get(method)
		if found:
			return {"recipient": found[0], "recipients": all_recipients, "method": method}

	return {"recipient": None, "recipients": all_recipients, "method": "Unresolved"}


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------


@frappe.whitelist()
def resolve_assignment(recipient_email: str, company: str | None = None) -> dict:
	"""Return the owner and manager chain for a recipient address.

	Exposed separately so mappings can be tested without ingesting mail.
	"""
	if not frappe.has_permission("Inquiry Ticket", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	user = get_sales_engineer_for_mailbox(recipient_email)
	managers = get_managers_for_user(user, company) if user else []
	return {
		"recipient": _normalise(recipient_email),
		"user": user,
		"managers": managers,
		"resolved": bool(user),
	}


# RFC 5322 msg-id: "<" id-left "@" id-right ">". Header values arrive either
# clean from n8n's resolved format or raw with the field name and folded
# whitespace still attached, so parse both through the same regex.
_MSGID_RE = re.compile(r"<[^<>\s]+@[^<>\s]+>")

# Letters and hyphens only, so a leading "Delivery-date:" is stripped while an
# ISO value like 2026-08-10T03:09:44Z -- which also contains a colon -- is not.
_HEADER_PREFIX_RE = re.compile(r"^\s*[A-Za-z][A-Za-z-]*:\s*")


def _as_datetime(value):
	"""Normalise whatever a caller sends into a datetime Frappe can store.

	``received_on`` and ``received_date`` are Datetime fields, and the callers are
	automation workflows handing over raw mail headers. This IMAP server returns
	some of them with the field name still attached ("Delivery-date: Mon, 10 Aug
	2026 03:09:44 +0000"), which no date parser accepts -- so the value silently
	became null and the SLA clock started from nothing.

	Accepts RFC 2822 header form and ISO, returns naive UTC so both paths agree,
	and returns None when the value cannot be understood so the caller's own
	fallback applies rather than a wrong timestamp being stored.
	"""
	if isinstance(value, (list, tuple)):
		value = value[0] if value else None
	if not value:
		return None

	text = _HEADER_PREFIX_RE.sub("", str(value)).strip()
	if not text:
		return None

	dt = None
	try:
		dt = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
	except ValueError:
		try:
			dt = parsedate_to_datetime(text)
		except (TypeError, ValueError):
			dt = None

	if dt is None:
		try:
			return get_datetime(text)
		except Exception:
			return None

	if dt.tzinfo is not None:
		dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
	return dt


def _collapse_ws(raw) -> str:
	"""Strip all whitespace from a header value.

	Used as the last-resort fallback when a value could not be parsed as a
	Message-ID. Storing the raw folded text instead would guarantee the value
	never matches itself on a later lookup.
	"""
	if raw is None:
		return ""
	if isinstance(raw, (list, tuple)):
		raw = raw[0] if raw else ""
	return re.sub(r"\s+", "", str(raw))


def _msgid_list(raw) -> list[str]:
	"""Extract Message-IDs from a header value, preserving their order."""
	if not raw:
		return []
	if isinstance(raw, (list, tuple)):
		text = " ".join(str(x) for x in raw)
	else:
		text = str(raw)

	# Unfold first. RFC 5322 wraps long headers onto continuation lines, and
	# Outlook's Message-IDs are long enough to wrap mid-id:
	#
	#     Message-ID: <CWLP302MB03493C11DA75793B53C4011CA8DE2@CW
	#      LP302MB0349.GBRP302.PROD.OUTLOOK.COM>
	#
	# _MSGID_RE excludes whitespace between the brackets, so a folded id matched
	# nothing and the bare-token fallback rejected it too (the fold introduces a
	# space). ingest_inquiry_email then stored an empty message_id, silently
	# disabling both deduplication and thread matching -- the same RFQ ingested
	# twice produced two tickets. A msg-id never legitimately contains
	# whitespace, and References entries stay separable because each keeps its
	# own angle brackets, so collapsing every space here is safe.
	text = re.sub(r"\s+", "", text)

	found = _MSGID_RE.findall(text)
	if not found:
		# Some senders omit the angle brackets. Fall back to the bare token,
		# but only when it still looks like a msg-id rather than prose.
		bare = text.split(":", 1)[-1]
		if bare and "@" in bare and "<" not in bare:
			found = [f"<{bare.strip('<>')}>"]

	seen, out = set(), []
	for m in found:
		if m not in seen:
			seen.add(m)
			out.append(m)
	return out


def _first_msgid(raw) -> str:
	ids = _msgid_list(raw)
	return ids[0] if ids else ""


def _ticket_by_message_id(msgid: str) -> str | None:
	"""The ticket whose *originating* email carries this Message-ID."""
	return frappe.db.get_value("Inquiry Ticket", {"message_id": msgid}, "name")


def _ticket_by_linked_email(msgid: str) -> str | None:
	"""The ticket this Message-ID is already attached to as a follow-up."""
	return frappe.db.get_value(
		"Inquiry Email", {"message_id": msgid, "parenttype": "Inquiry Ticket"}, "parent"
	)


@frappe.whitelist()
def find_inquiry_by_thread(
	message_id: str = "",
	in_reply_to: str = "",
	references: str = "",
) -> dict:
	"""Locate the ticket a message belongs to, following RFC 5322 threading.

	The old ``find_inquiry_by_message_id`` could only match a message against
	the ticket it *created*. A reply carries a brand-new Message-ID, so that
	lookup always missed and every customer reply opened a second ticket.

	Four probes, most specific first:

	1. Own Message-ID against ``Inquiry Ticket.message_id`` — the same mail
	   seen twice (a BCC copy, or a re-run of the same n8n execution).
	2. Own Message-ID against the linked-email child table — already attached.
	3. Ancestors from In-Reply-To and References against ticket originators.
	4. Ancestors against the child table — a reply to a reply.

	References is walked right-to-left because the rightmost entry is the
	nearest ancestor; matching left-to-right would attach a long thread to
	whichever mail happened to start it rather than the one being answered.

	Both columns are indexed (``Inquiry Ticket.message_id`` carries a search
	index, ``Inquiry Email.message_id`` is unique), so every probe is a key hit.
	"""
	if not frappe.has_permission("Inquiry Ticket", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	own = _first_msgid(message_id)

	if own:
		ticket = _ticket_by_message_id(own)
		if ticket:
			return _thread_result(ticket, "self", own)

		ticket = _ticket_by_linked_email(own)
		if ticket:
			return _thread_result(ticket, "self_linked", own)

	# Nearest ancestor first: In-Reply-To, then References right-to-left.
	ancestors = _msgid_list(in_reply_to) + list(reversed(_msgid_list(references)))
	seen = set()
	for parent in ancestors:
		if parent in seen:
			continue
		seen.add(parent)

		ticket = _ticket_by_message_id(parent)
		if ticket:
			return _thread_result(ticket, "in_reply_to", parent)

		ticket = _ticket_by_linked_email(parent)
		if ticket:
			return _thread_result(ticket, "references", parent)

	return {"found": False, "ticket": None, "match": None, "matched_message_id": None}


def _thread_result(ticket: str, match: str, matched_message_id: str) -> dict:
	row = (
		frappe.db.get_value(
			"Inquiry Ticket",
			ticket,
			["name", "status", "sales_engineer", "responsible_manager", "company"],
			as_dict=True,
		)
		or {}
	)
	return {
		"found": True,
		"ticket": ticket,
		"match": match,
		"matched_message_id": matched_message_id,
		"status": row.get("status"),
		"sales_engineer": row.get("sales_engineer"),
		"responsible_manager": row.get("responsible_manager"),
		"company": row.get("company"),
	}


@frappe.whitelist()
def find_inquiry_by_message_id(message_id: str) -> dict:
	"""Look up a ticket by Message-ID alone.

	Retained for callers that only have the one header. New code should call
	``find_inquiry_by_thread``, which also follows In-Reply-To and References.
	"""
	result = find_inquiry_by_thread(message_id=message_id)
	return {"found": result["found"], "ticket": result["ticket"]}


@frappe.whitelist()
def ingest_inquiry_email(payload: str | dict) -> dict:
	"""Create (or deduplicate) one Inquiry Ticket from one forwarded email.

	Idempotent on ``message_id``. Runs in the caller's transaction so a failure
	part-way leaves nothing behind.

	Returns ``{ticket, created, event, duplicate_of, assigned_to, manager,
	resolution_method, status}`` where ``event`` is one of ``created``,
	``reply`` or ``duplicate``.
	"""
	if not frappe.has_permission("Inquiry Ticket", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	data = json.loads(payload) if isinstance(payload, str) else (payload or {})
	settings = get_inquiry_settings()

	# Normalise before storing. n8n's resolved format gives a clean "<id@host>",
	# but the raw-header fallback yields "Message-ID:\n\t<id@host>". Storing the
	# unnormalised form would make dedup and thread lookups miss each other,
	# since find_inquiry_by_thread always compares the bracketed id.
	# Collapse whitespace rather than only trimming the ends: a folded header
	# that _first_msgid could not parse would otherwise be stored verbatim,
	# newlines and all, and never match itself on the next lookup.
	message_id = _first_msgid(data.get("message_id")) or _collapse_ws(data.get("message_id"))
	if not message_id:
		frappe.throw(_("message_id is required for idempotent ingestion."))

	headers = data.get("headers") or {}
	resolution = resolve_original_recipient(headers)

	# ---- 1. Deduplicate -----------------------------------------------------
	existing = frappe.db.get_value(
		"Inquiry Ticket", {"message_id": message_id}, ["name", "original_recipients"], as_dict=True
	)
	if existing:
		_merge_duplicate(existing, resolution, data)
		return {
			"ticket": existing.name,
			"created": False,
			"event": "duplicate",
			"duplicate_of": existing.name,
			"resolution_method": resolution["method"],
			"status": "duplicate",
		}

	# ---- 1b. Thread check ---------------------------------------------------
	# The automation layer already runs this lookup before classifying, which is
	# what keeps a reply from costing two LLM calls. It cannot be trusted as the
	# only check: n8n evaluates a node for *every* item before moving to the next
	# node, so when a thread's messages arrive in one IMAP poll the lookup runs
	# against a database that does not yet contain the parent ticket -- it is
	# created further down the same pass. Three messages of one conversation
	# arriving together therefore produced three tickets.
	#
	# Repeating the check here fixes that, because ingestion is sequential and
	# transactional: by the time the reply is ingested the parent is committed.
	thread = find_inquiry_by_thread(
		message_id=message_id,
		in_reply_to=data.get("in_reply_to") or "",
		references=data.get("references") or "",
	)
	if thread["found"]:
		attach_email_to_ticket(
			ticket=thread["ticket"],
			message_id=message_id,
			direction="Incoming",
			subject=data.get("subject") or "",
			email_from=(headers.get("from_email") or ""),
			email_to=resolution["recipient"] or "",
			thread_id=data.get("references") or "",
			received_on=data.get("received_date") or "",
		)
		return {
			"ticket": thread["ticket"],
			"created": False,
			"event": "reply",
			"thread_match": thread["match"],
			"assigned_to": thread.get("sales_engineer"),
			"resolution_method": resolution["method"],
			"status": "reply",
		}

	# ---- 2. Resolve owner and managers -------------------------------------
	company = data.get("company") or _default_company()
	owner_user = get_sales_engineer_for_mailbox(resolution["recipient"]) if resolution["recipient"] else None
	managers = get_managers_for_user(owner_user, company) if owner_user else []
	responsible_manager = managers[0]["manager"] if managers else None

	# ---- 3. Match the customer ---------------------------------------------
	contact = data.get("contact") or {}
	customer, lead = _match_or_create_party(contact, company)

	# ---- 4. Opportunity -----------------------------------------------------
	# Never let CRM bookkeeping cost us the ticket. The Inquiry Ticket is this
	# system's record of the customer's request; the Opportunity is a downstream
	# convenience. Because this runs before ticket.insert(), an exception here
	# used to abort the request and roll the ticket back with it -- a mandatory
	# field on a customised Opportunity silently discarded the whole inquiry.
	try:
		project, project_match = _match_or_create_project(
			(data.get("inquiry") or {}).get("project_name"), customer, company
		)
	except Exception:
		frappe.log_error(
			title="Inquiry intake: Project match failed",
			message=f"message_id={message_id}\n\n{frappe.get_traceback()}",
		)
		project, project_match = None, "Unmatched"

	try:
		opportunity = _ensure_opportunity(customer, lead, company, owner_user, project)
		# An Opportunity reused from an earlier inquiry may predate project
		# matching, or have been opened before the project was known. Fill the
		# gap, but never overwrite a value a human has already chosen.
		if opportunity and project and not frappe.db.get_value(
			"Opportunity", opportunity, "custom_project"
		):
			frappe.db.set_value(
				"Opportunity", opportunity, "custom_project", project, update_modified=False
			)
	except Exception:
		frappe.log_error(
			title="Inquiry intake: Opportunity creation failed",
			message=f"message_id={message_id}\n\n{frappe.get_traceback()}",
		)
		opportunity = None

	# ---- 5. Create the ticket ----------------------------------------------
	unresolved = not owner_user
	ticket = frappe.get_doc(
		{
			"doctype": "Inquiry Ticket",
			"company": company,
			"status": "Pending Review" if unresolved else "New",
			"priority": data.get("priority") or "Medium",
			"inquiry_type": data.get("classification") or "",
			"original_email_subject": data.get("subject"),
			"received_date": _as_datetime(data.get("received_date")),
			"original_sent_date": _as_datetime(data.get("sent_date")),
			"message_id": message_id,
			"original_recipient": resolution["recipient"],
			"original_recipients": "\n".join(resolution["recipients"]),
			"forwarding_mailbox": _normalise(settings.get("forwarding_mailbox") if settings else None),
			"recipient_resolution_method": resolution["method"],
			# source_mailbox drives the existing before_insert auto-assignment, so it
			# must carry the ORIGINAL recipient, never the funnel address.
			"source_mailbox": resolution["recipient"],
			"sales_engineer": owner_user,
			"responsible_manager": responsible_manager,
			"company_name": contact.get("company_name"),
			"contact_person": _full_name(contact),
			"contact_first_name": contact.get("first_name"),
			"contact_last_name": contact.get("last_name"),
			"contact_email": contact.get("email"),
			"contact_phone": _first_phone(contact),
			"customer": customer,
			"lead": lead,
			"opportunity": opportunity,
			"project": project,
			"project_match_method": project_match,
			"customer_match_method": data.get("match_method") or "",
			"ai_classification": data.get("classification"),
			"ai_confidence": data.get("confidence") or 0,
			"ai_provider": data.get("ai_provider"),
			"ai_summary": data.get("summary"),
			"ai_extracted_data": json.dumps(data.get("extracted") or {}, ensure_ascii=False),
			"ai_needs_review": 1 if (unresolved or _low_confidence(data, settings)) else 0,
			"delivery_location": (data.get("inquiry") or {}).get("delivery_location"),
			"due_date": (data.get("inquiry") or {}).get("due_date"),
			"tender_number": (data.get("inquiry") or {}).get("tender_number"),
			"line_items": _build_line_items(data.get("items")),
		}
	)
	ticket.insert()

	# ---- 6. Attach the source email ----------------------------------------
	_append_email(ticket, data, resolution, direction="Incoming")

	create_audit_event(
		entity_type="Inquiry Ticket",
		entity_id=ticket.name,
		action="Inquiry Ingested",
		details=(
			f"Ingested from {resolution['recipient'] or 'unresolved recipient'} "
			f"via {resolution['method']}; owner={owner_user or 'unassigned'}; "
			f"message_id={message_id}"
		),
	)

	return {
		"ticket": ticket.name,
		"created": True,
		"event": "created",
		"duplicate_of": None,
		"assigned_to": owner_user,
		"manager": responsible_manager,
		"resolution_method": resolution["method"],
		"status": ticket.status,
	}


@frappe.whitelist()
def attach_email_to_ticket(
	ticket: str,
	message_id: str = "",
	direction: str = "Incoming",
	subject: str = "",
	email_from: str = "",
	email_to: str = "",
	thread_id: str = "",
	received_on: str = "",
	email_file: str = "",
) -> dict:
	"""Append a follow-up email to an existing ticket (thread sync, FR-27/28).

	Replaces the ``kayan-eg.net/api/v1/erpnext/attach-email`` endpoint that
	workflow 04 has been calling since June and which was never built.
	"""
	if not frappe.has_permission("Inquiry Ticket", "write", ticket):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Inquiry Ticket", ticket)

	# Same normalisation as ingest_inquiry_email, so the child table and the
	# thread lookup are always comparing the identical bracketed form.
	message_id = _first_msgid(message_id) or _collapse_ws(message_id)
	thread_id = _first_msgid(thread_id) or _collapse_ws(thread_id)

	if message_id and any((row.message_id or "") == message_id for row in doc.emails or []):
		return {"ticket": ticket, "appended": False, "reason": "already linked"}

	# Inquiry Email.message_id is globally unique, so a message already linked to
	# a *different* ticket would raise DuplicateEntryError on save. Report it
	# instead: it means the thread lookup and the caller disagree about ownership.
	if message_id:
		other = _ticket_by_linked_email(message_id)
		if other and other != ticket:
			return {
				"ticket": other,
				"appended": False,
				"reason": f"already linked to {other}",
			}

	doc.append(
		"emails",
		{
			"message_id": message_id,
			"thread_id": thread_id,
			"direction": direction,
			"subject": subject,
			"email_from": email_from,
			"email_to": email_to,
			"received_on": _as_datetime(received_on) or frappe.utils.now_datetime(),
			"email_file": email_file or None,
		},
	)
	doc.save(ignore_permissions=True)

	create_audit_event(
		entity_type="Inquiry Ticket",
		entity_id=ticket,
		action=f"{direction} Email Linked",
		details=f"subject={subject or '(none)'}; message_id={message_id or '(none)'}",
	)
	return {"ticket": ticket, "appended": True}


@frappe.whitelist()
def send_escalation(ticket: str, breach_type: str = "", level: int = 1) -> dict:
	"""Notify the escalation chain for a breached SLA (FR-36/37).

	Replaces ``kayan-eg.net/api/v1/notifications/escalate``, which workflow 05
	calls and which was never built. It also fills the gap in
	``sla_monitor.check_sla_breaches``, which flags breaches but notifies nobody
	— the reason every existing ticket sat at ``Breached`` unremarked.
	"""
	if not frappe.has_permission("Inquiry Ticket", "read", ticket):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Inquiry Ticket", ticket)
	managers = get_managers_for_user(doc.sales_engineer, doc.company) if doc.sales_engineer else []

	try:
		level = int(level or 1)
	except (TypeError, ValueError):
		level = 1

	targets = [m for m in managers if (m["escalation_level"] or 1) <= level] or managers[:1]
	recipients = []
	for m in targets:
		email = frappe.db.get_value("User", m["manager"], "email")
		if email and email not in recipients:
			recipients.append(email)

	if not recipients:
		create_audit_event(
			entity_type="Inquiry Ticket",
			entity_id=ticket,
			action="SLA Escalation Failed",
			details=f"No escalation recipients resolved for owner {doc.sales_engineer or '(unassigned)'}",
		)
		return {"status": "skipped", "reason": "no escalation recipients resolved"}

	frappe.sendmail(
		recipients=recipients,
		subject=f"SLA {breach_type or 'breach'}: {doc.name} ({doc.company_name or ''})",
		message=(
			f"<p>Inquiry <b>{doc.name}</b> has breached its {breach_type or 'SLA'}.</p>"
			f"<p>Status: {doc.status}<br>Owner: {doc.sales_engineer or 'unassigned'}<br>"
			f"Subject: {doc.original_email_subject or '-'}</p>"
			f'<p><a href="{frappe.utils.get_url()}/app/inquiry-ticket/{doc.name}">Open ticket</a></p>'
		),
		reference_doctype="Inquiry Ticket",
		reference_name=doc.name,
	)

	frappe.db.set_value("Inquiry Ticket", ticket, "sla_status", "Escalated", update_modified=False)
	create_audit_event(
		entity_type="Inquiry Ticket",
		entity_id=ticket,
		action="SLA Escalated",
		details=f"{breach_type or 'SLA breach'} escalated to {', '.join(recipients)}",
	)
	return {"status": "sent", "recipients": recipients, "level": level}


# ----------------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------------


def _merge_duplicate(existing, resolution, data):
	"""Fold an additional copy of an already-ingested email into its ticket.

	A BCC-distributed RFQ arrives once per solicited recipient. Each copy names a
	different person, so every recipient is recorded even though only one ticket
	exists and only one person owns it.
	"""
	known = [r for r in (existing.original_recipients or "").splitlines() if r.strip()]
	added = [r for r in resolution["recipients"] if r not in known]
	if added:
		frappe.db.set_value(
			"Inquiry Ticket",
			existing.name,
			"original_recipients",
			"\n".join(known + added),
			update_modified=False,
		)

	create_audit_event(
		entity_type="Inquiry Ticket",
		entity_id=existing.name,
		action="Duplicate Email Merged",
		details=(
			f"Duplicate copy of message_id={data.get('message_id')} "
			f"addressed to {', '.join(added) or 'no new recipients'}"
		),
	)


def _default_company() -> str | None:
	return frappe.defaults.get_defaults().get("company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


def _low_confidence(data, settings) -> bool:
	threshold = (settings.get("confidence_threshold") if settings else None) or 75
	try:
		return float(data.get("confidence") or 0) < float(threshold)
	except (TypeError, ValueError):
		return True


def _full_name(contact: dict) -> str | None:
	parts = [contact.get("first_name"), contact.get("last_name")]
	name = " ".join(p for p in parts if p)
	return name or contact.get("name") or None


def _first_phone(contact: dict) -> str | None:
	phones = contact.get("phones") or []
	if isinstance(phones, str):
		return phones
	return phones[0] if phones else None


def _match_or_create_party(contact: dict, company: str | None):
	"""Match an existing Customer, else an existing Lead, else create a Lead.

	Matching is by EMAIL first. Names are unreliable here: the same person is
	transliterated differently between the From display name and the body
	signature ("Eng.Treiz Abdel Meseeh" vs "Eng. Teriza Abd El Maseeh"), which is
	common for Arabic-origin names.
	"""
	email = _normalise(contact.get("email"))
	company_name = (contact.get("company_name") or "").strip()

	if email:
		customer = frappe.db.get_value("Customer", {"email_id": email}, "name")
		if customer:
			return customer, None

	if company_name:
		customer = frappe.db.get_value("Customer", {"customer_name": company_name}, "name")
		if customer:
			return customer, None

	if email:
		lead = frappe.db.get_value("Lead", {"email_id": email}, "name")
		if lead:
			return None, lead

	lead_doc = frappe.get_doc(
		{
			"doctype": "Lead",
			"lead_name": _full_name(contact) or email or "Unknown",
			"company_name": company_name,
			"email_id": email or "",
			"phone": _first_phone(contact) or "",
			"status": "Open",
		}
	)
	lead_doc.insert(ignore_permissions=True)
	return None, lead_doc.name


def _normalise_project_name(raw) -> str:
	"""Fold a project name to a comparable key.

	Kayan's Project master is hand-entered and inconsistent -- one live record is
	literally ``"G3 MALL "`` with a trailing space -- while the name we extract
	comes off a subject line. Comparing raw strings would miss almost every real
	match and create a duplicate Project instead, so both sides are folded to
	lowercase alphanumerics before comparison.
	"""
	return re.sub(r"[^a-z0-9]+", "", (raw or "").lower())


def _match_or_create_project(project_name, customer=None, company=None):
	"""Resolve an extracted project name to a Project, creating one if needed.

	Returns ``(project, method)`` where method is Exact, Created or Unmatched, so
	the ticket records how the link was arrived at. 'Created' is the one worth
	auditing: a near-miss on the name opens a duplicate Project rather than
	joining the existing one.
	"""
	name = (project_name or "").strip()
	if not name:
		return None, "Unmatched"

	key = _normalise_project_name(name)
	if not key:
		return None, "Unmatched"

	for row in frappe.get_all("Project", fields=["name", "project_name"], limit_page_length=0):
		if _normalise_project_name(row.project_name) == key:
			return row.name, "Exact"

	# No match: open one. Project may carry mandatory customisations the way
	# Opportunity does, and the same rule applies -- a CRM record must never cost
	# us the inquiry, so this is best-effort and the caller tolerates None.
	proj = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": name,
			"status": "Open",
			"is_active": "Yes",
			"company": company or _default_company(),
			"customer": customer or None,
		}
	)
	proj.flags.ignore_mandatory = True
	proj.insert(ignore_permissions=True)
	return proj.name, "Created"


def _ensure_opportunity(customer, lead, company, owner_user=None, project=None):
	"""Link an open Opportunity for the party, creating one when absent.

	Kayan customise Opportunity with mandatory fields that only a human can
	supply at qualification: contractor, consultant, owner/end user, project,
	project sector and scope of supply are commercial facts, not something an
	inbound RFQ carries. Intake therefore inserts a skeleton with
	``ignore_mandatory`` and fills only what it can honestly know. Validation
	still fires the moment a sales engineer opens the record and saves it, so
	the completeness requirement moves to the person who can actually satisfy
	it rather than blocking ingestion.
	"""
	party = customer or lead
	if not party:
		return None

	party_type = "Customer" if customer else "Lead"
	existing = frappe.db.get_value(
		"Opportunity",
		{"opportunity_from": party_type, "party_name": party, "status": "Open"},
		"name",
	)
	if existing:
		return existing

	opp = frappe.get_doc(
		{
			"doctype": "Opportunity",
			"opportunity_from": party_type,
			"party_name": party,
			"company": company,
			"status": "Open",
			# The custom mandatory fields intake can fill honestly.
			"opportunity_owner": owner_user or None,
			"custom_project": project or None,
		}
	)
	opp.flags.ignore_mandatory = True
	opp.insert(ignore_permissions=True)
	return opp.name


def _build_line_items(items) -> list:
	"""Map extracted items to Inquiry Line Item rows.

	Rows without a description are dropped. The extraction prompt shows the model
	an example schema containing ``{"description": "", "quantity": 0, "uom": ""}``,
	and when an email has no itemised list the model tends to echo that empty
	placeholder back rather than return an empty array. item_description is
	mandatory on Inquiry Line Item, so passing it through raised MandatoryError
	and cost us the whole ticket -- for a row that carried no information anyway.
	"""
	rows = []
	for item in items or []:
		description = (item.get("description") or item.get("item_description") or "").strip()
		if not description:
			continue
		idx = len(rows) + 1
		rows.append(
			{
				"line_no": idx,
				"item_description": item.get("description") or item.get("item_description") or "",
				"quantity": item.get("quantity") or 0,
				"uom": item.get("uom") or "Nos",
				"customer_item_code": item.get("customer_item_code"),
				"requested_brand": item.get("brand"),
				"delivery_location": item.get("delivery_location"),
				"required_date": item.get("required_date"),
				"matched_by_ai": 1 if item.get("matched_by_ai") else 0,
			}
		)
	return rows


def _append_email(ticket, data, resolution, direction="Incoming"):
	"""Record the source email against the ticket.

	NOTE: Inquiry Email has no body field — it stores headers plus an
	``email_file`` Link to a File. The message body and attachments are uploaded
	separately by the automation layer and linked through that field, which keeps
	large RFQ bodies and multi-megabyte BoQ attachments out of the database.
	"""
	headers = data.get("headers") or {}
	cc = headers.get("cc") or []
	ticket.append(
		"emails",
		{
			"message_id": data.get("message_id"),
			"thread_id": data.get("thread_id"),
			"direction": direction,
			"subject": data.get("subject"),
			"email_from": headers.get("from_email"),
			"email_to": resolution["recipient"] or "",
			"cc": "\n".join(cc) if isinstance(cc, list) else (cc or ""),
			"received_on": _as_datetime(data.get("received_date")),
			"email_file": data.get("email_file"),
		},
	)
	ticket.save(ignore_permissions=True)
