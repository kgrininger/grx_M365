# GRX M365 Audit

## Scope

Reviewed modules:

- `grx_m365/api/bookings.py`
- `grx_m365/api/calendar_pull.py`
- `grx_m365/api/auth.py`

## 1. Customer Fields

Observed fields:

- `customer_name`
- `customer_email`
- `customer_phone`

Assessment:

- These are booking payload fields, not GRX Customer master fields.
- They are used for Microsoft Graph payload creation and booking submission.
- No GRX Customer shadow model is implemented here.

## 2. Contact Fields

Observed contact-like data:

- email addresses from Microsoft Graph events and profile
- attendee/organizer resolution by email

Assessment:

- Contact-like data exists as external identity data.
- There is no strong in-app Contact master modeling here.
- The app is integration-oriented, not contact-master oriented.

## 3. Address Fields

Observed:

- no meaningful Address master behavior in reviewed code

Assessment:

- Address is not a core concern of this app.
- No Address shadow truth is visible in the reviewed implementation.

## 4. Communication Audit

Assessment:

- Communication-like behavior is present through calendar and booking payloads.
- The app does not own GRX Communication as master data.
- It integrates with external email/calendar systems.

## 5. Device-First Audit

Assessment:

- PASS

Reason:

- The app is not customer-first in the GRX sense.
- It is external-system-first and mostly payload-driven.
- No meaningful legacy GRX customer container dominates the design.

## 6. Shadow Truths

Low:

- `customer_name`
- `customer_email`
- `customer_phone`

Assessment:

- These are payload fields, not shadow master-data truths.
- They are acceptable as integration inputs.

## 7. Consolidation Plan

Recommended:

1. keep booking payloads as-is
2. avoid introducing GRX Customer shadow fields here
3. keep external contact data aligned with the contact-first model only at the integration boundary

