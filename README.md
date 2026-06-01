# Kayan Inquiry Management

AI-Powered Email Inquiry Management & Quotation Workflow for ERPNext v16.

## Overview

A custom ERPNext v16 application that automates customer inquiry intake, classification, assignment, technical review, quotation management, approval workflows, and SLA monitoring.

### Key Features

- **AI Email Processing** — Monitors 35-40 IMAP mailboxes, classifies inquiries using AI, extracts structured data from emails and attachments
- **Inquiry Lifecycle Management** — 14-state workflow from New → Won/Lost with full audit trail
- **Multi-Company Support** — Company-level data segregation with configurable workflows per company
- **Assignment Engine** — Auto-assigns Sales Engineers by mailbox mapping; supports multiple Application Engineers
- **Quotation Workspace** — Prepare quotations, manage revisions, generate ERPNext Quotation records
- **Approval Workflow** — Configurable multi-level approvals (up to 4 levels) with value-based thresholds
- **SLA Monitoring** — Configurable SLA timers with automated escalation chains
- **Reporting & Analytics** — Operational dashboards, KPIs, conversion tracking

## Installation

```bash
bench get-app https://github.com/kayan-automation/kayan_inquiry_management.git
bench --site your-site install-app kayan_inquiry_management
bench --site your-site migrate
```

## Requirements

- ERPNext v16
- Frappe Framework v16
- Python 3.14+
- MariaDB 10.6+
- Redis 7.0+

## Companion Service

This app works with the **Kayan AI Platform** (`kayan_ai_platform`) for:
- IMAP email collection
- AI classification & extraction
- OCR processing
- Customer matching

## License

GPL-3.0
