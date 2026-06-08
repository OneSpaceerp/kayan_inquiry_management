# Kayan Inquiry Management - ERPNext User Manual

This manual provides a step-by-step guide on how to configure settings, manage records, and monitor the automated inquiry workflow within the **Kayan Inquiry Management** application in ERPNext v16.

---

## 1. App Configuration Settings

The system relies on a singleton configuration document called **Inquiry Settings** to manage AI thresholds, SLAs, escalations, and multi-level approvals.

### How to access:
1. Log in to ERPNext as an **Administrator** or **Inquiry Coordinator**.
2. Search for **Inquiry Settings** in the global Search Bar.
3. Open the single settings record.

### Configuration Fields & Details:

| Section | Field Name | Description | Recommended Value |
| :--- | :--- | :--- | :--- |
| **AI Settings** | `confidence_threshold` | Minimum confidence score (%) required from the AI classifier to auto-extract items without manual review. | `75` |
| | `default_ai_provider` | Selected AI provider for email classification and data extraction (`Gemini`, `OpenAI`, `Claude`, `Local`). | `Gemini` |
| | `preferred_language` | Preferred language for AI classification prompts (`English`, `Arabic`). | `English` |
| | `ai_api_key` | Optional API key if calling the model provider directly instead of through the gateway. | *(Blank or local key)* |
| **SLA Config** | `assignment_sla_hours` | Hours allowed to transition from `New` status to `Assigned to Sales Engineer`. | `4` |

> [!NOTE]
> **AI Execution Context:** The automation workflows run directly in **n8n**. The AI API key and model selection are managed securely within n8n credentials (`Gemini API Token`), so you can leave the `ai_api_key` and any platform URL fields blank in the ERPNext settings UI.

### How to configure SLAs:
| | `technical_sla_hours` | Hours allowed for Application Engineers to complete the technical review. | `24` |
| | `quotation_sla_hours` | Hours allowed to prepare and send the final quotation. | `48` |
| | `sla_business_hours_only` | Check to only calculate SLA during business hours. | `Unchecked` |
| **Notifications**| `email_notifications_enabled`| Enable outbound SMTP notification emails. | `Checked` |
| | `erp_notifications_enabled` | Enable internal ERPNext system alerts. | `Checked` |
| **Escalations** | `escalation_direct_manager` | User link representing the first level of SLA breach warning. | *(Select manager user)* |
| | `escalation_sales_manager` | User link representing the second level manager. | *(Select sales manager)* |
| | `escalation_department_manager`| User link representing the department head. | *(Select department head)* |
| **Approvals** | `approval_level_1_role` | Role representing the first approval stage for quotes < 50k. | `Sales Manager` |
| | `approval_level_2_role` | Role representing the second approval stage for quotes < 200k. | `Commercial Director` |
| | `approval_level_3_role` | Role representing the third approval stage for quotes >= 200k. | `General Manager` |
| | `approval_level_4_role` | Optional fourth approval stage. | `Accounts Manager` |

> [!IMPORTANT]
> Ensure that active users are assigned to the roles selected in **Approval Level Roles** (e.g., *Sales Manager*, *Commercial Director*, *General Manager*) so they can receive approval requests. If a role is empty, notifications will fallback to `kelshiekh@gmail.com`.

---

## 2. Setting Up Mappings

Before processing incoming emails, two mapping lists must be configured to enable auto-assignment and multi-company support:

### A. Mailbox Mapping
Maps incoming sales inboxes to dedicated **Sales Engineers**.
1. Search for **Mailbox Mapping** in the search bar.
2. Click **Add Mailbox Mapping**.
3. Fill in:
   - **Mailbox:** The incoming email address (e.g. `inquiries-inbox@kayan-eg.net`).
   - **Sales Engineer:** Select the ERPNext user.
   - **Active:** Check to enable.

### B. Domain Mapping
Maps customer domains to the correct ERPNext **Company** entity.
1. Search for **Domain Mapping** in the search bar.
2. Click **Add Domain Mapping**.
3. Fill in:
   - **Email Domain:** The domain name (e.g. `abc.com` or `trending-mena.com`).
   - **Company:** The target ERPNext company (e.g. `KAYAN IMPORT`).
   - **Active:** Check to enable.

---

## 3. Inquiry Records & AI Processing

All incoming emails classified as RFQs/Tenders are registered as **Inquiry Tickets**.

### How to Review Records:
1. Search for **Inquiry Ticket** list.
2. Each ticket displays:
   - **Status:** Shows current stage in the pipeline.
   - **AI Needs Review:** If checked (`1`), the classification confidence was below the configured threshold, or manual verification is required.
   - **AI Confidence:** The confidence score of the classification.
   - **Source Mailbox:** The email address where the RFQ was received.
   - **Customer:** Linked ERPNext Customer.
   - **SLA Status:** Displayed as `Active`, `Met`, `Breached`, or `Escalated`.

### Customer Matching & Creation
The system automatically matches customers using the following sequence:
1. **Company Name:** Search for an existing Customer matching the extracted company name.
2. **Email Domain:** Search for an existing Customer with the same email domain.
3. **Email Address:** Search for an existing Lead or Contact.
4. **Auto-Lead Creation:** If no match is found, a new **Lead** is automatically created in ERPNext, followed by an **Opportunity** linked to the Inquiry.

---

## 4. Quotation Preparation & Approvals

When an Inquiry progresses to the **Quotation Preparation In Progress** stage:
1. The Application Engineer fills in the **Line Items** and **Estimated Value**.
2. When ready, the engineer updates the status to **Pending Approval**.
3. The system checks the `estimated_value` and determines the approval levels:
   - `< 50,000 EGP` -> Requires Level 1 approval.
   - `< 200,000 EGP` -> Requires Level 1 & 2 approvals.
   - `>= 200,000 EGP` -> Requires Level 1, 2, & 3 approvals.
4. Approvers receive an email with **Approve** and **Reject** links.
5. Once fully approved, the status is updated to **Approved**, and the system automatically generates a standard **ERPNext Quotation** with all line items and links it back to the Inquiry Ticket.
