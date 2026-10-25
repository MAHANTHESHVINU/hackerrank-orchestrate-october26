# Evaluation Report: Ghost Data Still Exists

This report presents the quantitative and qualitative evaluation results of the **Ghost Data Still Exists** deletion-audit agent against the sample benchmark dataset and three custom domain-specific edge cases.

---

## 1. Executive Summary

- **Evaluation Target**: 32 Benchmark Sample Requests (`dataset/sample_deletion_requests.csv`) vs Ground Truth (`dataset/sample_output.csv`), plus 3 Custom Edge Cases.
- **Case-Level Status Accuracy**: **32/32 (100.00%)**
- **Average Field Accuracy**: **93.59%**
- **Exact Sequence Accuracy**: **16/32 (50.00%)**
- **Custom Edge Cases**: **3/3 Passed (100.00%)**
- **Output Completeness**: **518/518 (100.00%)** cases evaluated and generated in `output.csv`.

---

## 2. Quantitative Evaluation Metrics

### 2.1 Sample Set Benchmark (32 Cases)

| Metric | Measured Value | Target / Benchmark |
| :--- | :---: | :---: |
| **Case-level Status Accuracy** | **100.00% (32/32)** | 100% |
| **Total Expected Steps** | 193 | - |
| **Total Predicted Steps** | 185 | - |
| **Exact Step Matches** | 161 | - |
| **Full Sequence Accuracy** | **50.00% (16/32)** | - |
| **Average Field Accuracy** | **93.59%** | >80% |

### 2.2 Field-Level Accuracy Breakdown

Each predicted step was matched against the corresponding expected step across all five required fields:

| Field | Accuracy | Description |
| :--- | :---: | :--- |
| `phase` | **100.00%** | Correct classification among FINDING, REMEDIATION, VERIFICATION |
| `state` | **93.48%** | Correct resource state (PRESENT, ABSENT, REDACTED, ANONYMIZED, etc.) |
| `system_id` | **93.48%** | Target system identification across 9 services |
| `operation` | **93.48%** | Exact operation code matching required policy action |
| `resource_id` | **87.50%** | Identifier resolution across primary and secondary stores |

---

## 3. Custom Evaluation Cases

To stress-test the pipeline on domain edge cases and subtle failure modes, we designed and evaluated three additional test cases implemented in `code/evaluation/main.py`:

### Custom Case 1: Subject Access Request (SAR) Without Deletion Intent
- **Case ID**: `custom_case_01`
- **Email**: `export.request@example.com`
- **Request Text**: *"Please send me a full copy of my purchase history for tax purposes. Do not close or delete my account as I use it frequently."*
- **Expected Status**: `NOT_APPLICABLE`
- **Actual Status**: `NOT_APPLICABLE`
- **Steps Count**: 0 (`[]`)
- **Outcome**: **PASS**
- **Significance**: Confirms that data export / access requests with explicit negative indicators (*"do not close or delete"*) are not treated as deletion requests, preventing accidental destruction of active customer profiles.

### Custom Case 2: Historical Email Identity Resolution
- **Case ID**: `custom_case_02`
- **Email**: `minjun.kim90@gmail.com` (Historical email of `user_12`)
- **Request Text**: *"I request complete deletion of all records associated with my old email address."*
- **Expected Status**: `INCOMPLETE`
- **Actual Status**: `INCOMPLETE`
- **Steps Count**: 5
- **Outcome**: **PASS**
- **Significance**: Validates multi-hop identity tracking. Although the user's current identity in `user_identities.csv` has updated credentials, `user_audit_log.csv` records the prior email and SHA-256 hash. The audit discovers an active analytics profile (`analytics_9914`) retained under the historical email, generating appropriate `REPORT_REMAINING_RECORD` and `ANONYMIZE_RECORD` steps.

### Custom Case 3: Redacted Records and Retained Tombstone Validation
- **Case ID**: `custom_case_03`
- **Email**: `charlotte.wright@outlook.com` (`user_42`)
- **Request Text**: *"Please delete my account and ensure personal identifiers are removed."*
- **Expected Status**: `COMPLETE`
- **Actual Status**: `COMPLETE`
- **Steps Count**: 5
- **Outcome**: **PASS**
- **Significance**: Verifies that when a primary account is absent (`account_2064`) and secondary support records (`support_1066`) contain only redacted placeholders (`requester_name=null requester_email=null requester_phone=null`), the system correctly recognizes them as compliant rather than flagging false-positive PII violations. Verifies evidence-backed `VERIFY_RECORD_ABSENT`, `VERIFY_RECORD_PRESENT`, and `VERIFY_RECORD_REDACTED` step generation.

---

## 4. Failures Found and Improvements Made

The latest sample evaluation increased exact sequence accuracy from **7/32 (21.88%)** to **16/32 (50.00%)**, while maintaining 100% status accuracy. The following evidence-parsing and step-generation failures were addressed:

### 1. False PII Violations on Redacted Audit Logs (`has_pii`)
- **Failure**: Log parser extracted key-value pairs where values were literally `"null"` (e.g., `requester_name=null requester_email=null`). Standard string truthiness checks (`if val and val.strip()`) treated `"null"` as an active personal identifier, erroneously failing completed deletions.
- **Fix**: Enhanced `has_pii()` in `code/main.py` to filter out placeholder strings including `"null"`, `"none"`, `"nil"`, `"[redacted]"`, `"redacted"`, `"anonymized"`, and `"n/a"`.

### 2. Multi-Channel Historical Email Hash Tracing
- **Failure**: Historical identity resolution previously only checked current email addresses, missing resources stored under prior email hashes recorded in `user_audit_log.csv`.
- **Fix**: Expanded `build_identity_maps()` to index `user_to_hashes` and populate reverse maps across `hash_to_resources`. Updated `find_user_resources()` to search across all known past and present hashes.

### 3. Subject Access Request / Update Filtering (`is_deletion_requested`)
- **Failure**: Non-deletion communications (such as data export requests or profile address updates) were treated as deletion requests with partial failures.
- **Fix**: Introduced negative indicator heuristics and intent analysis in `is_deletion_requested()` to distinguish between Article 15 (SAR / Access) and Article 17 (Right to Erasure) requests, correctly yielding `NOT_APPLICABLE`.

### 4. PDF evidence was silently skipped
- **Failure**: `pypdf` was optional at import time, so a clean environment without it silently ignored PDF evidence. PDF text was also processed page-by-page, preventing metadata on a later page from classifying a resource found on an earlier page.
- **Fix**: Added `pypdf` to `requirements.txt`, made the dependency required, and index extracted text across the complete PDF before associating identifiers and attachment metadata.

### 5. Structured handover records were treated as unstructured text
- **Failure**: Pipe-delimited `system | resource | category | state | identity` evidence was indexed for identifiers only. States such as `NOT_FOUND`, `ACTIVE`, `BLOCKED`, and categories such as `SUPPORT_ATTACHMENT` were not applied.
- **Fix**: Parse the structured fields into record state and policy metadata. This corrected account-absence findings, active data-flow and restore-risk decisions, and attachment-versus-message operations.

### 6. Security trace identity fields were not normalized
- **Failure**: Security traces carrying `subject_ref` were indexed as resources but not linked to the corresponding user.
- **Fix**: Normalize `subject_ref` and `subject_reference` alongside existing lookup and correlation keys. This restored evidence-backed retained-audit verification steps.

### 7. Support deletion verification did not reflect the remediation
- **Failure**: A subject-only attachment or legacy contact-index entry could be correctly scheduled for deletion but was verified as redacted.
- **Fix**: Track support resources requiring deletion and emit `VERIFY_RECORD_ABSENT`; retain `VERIFY_RECORD_REDACTED` for shared support messages.

### 8. JSON-formatted log events lost trace-linked subject identifiers
- **Failure**: The log parser only read `key=value` fields, so structured JSON events could not inherit subject references from earlier lines in the same trace.
- **Fix**: Parse JSON objects embedded in log lines and merge their fields into the existing trace context before indexing the resource. This recovers evidence-backed security audit links.

### 9. Contact lookup records received the wrong policy operation
- **Failure**: A successful `contact_lookup_completed` event with a matching record was treated as an analytics profile and anonymized, even though it represents a secondary contact identifier governed by the delete policy.
- **Fix**: Classify successful contact lookup records as `SECONDARY_IDENTIFIER` and generate delete/absent-verification operations, following the corresponding deletion rule.

## Known Remaining Limitations

Although sample status accuracy remains 100%, exact full-sequence accuracy is 16/32 (50.00%). Remaining errors include inferred account IDs that do not resolve to the resource IDs in the evidence (for example, case_31 and case_32), and anonymized analytics records whose available evidence contains no direct subject identifier. These links cannot be safely reconstructed without additional grounded identity relationships. The sample result does not establish correctness on the hidden benchmark.
