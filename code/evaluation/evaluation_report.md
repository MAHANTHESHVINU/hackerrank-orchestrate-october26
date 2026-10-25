# Evaluation Report: Ghost Data Still Exists

This report presents the quantitative and qualitative evaluation results of the **Ghost Data Still Exists** deletion-audit agent against the sample benchmark dataset and three custom domain-specific edge cases.

---

## 1. Executive Summary

- **Evaluation Target**: 32 Benchmark Sample Requests (`dataset/sample_deletion_requests.csv`) vs Ground Truth (`dataset/sample_output.csv`), plus 3 Custom Edge Cases.
- **Case-Level Status Accuracy**: **32/32 (100.00%)**
- **Average Field Accuracy**: **82.78%**
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
| **Exact Step Matches** | 125 | - |
| **Full Sequence Accuracy** | **21.88% (7/32)** | - |
| **Average Field Accuracy** | **82.78%** | >80% |

### 2.2 Field-Level Accuracy Breakdown

Each predicted step was matched against the corresponding expected step across all five required fields:

| Field | Accuracy | Description |
| :--- | :---: | :--- |
| `phase` | **96.67%** | Correct classification among FINDING, REMEDIATION, VERIFICATION |
| `state` | **82.22%** | Correct resource state (PRESENT, ABSENT, REDACTED, ANONYMIZED, etc.) |
| `system_id` | **81.11%** | Target system identification across 9 services |
| `operation` | **79.44%** | Exact operation code matching required policy action |
| `resource_id` | **74.44%** | Identifier resolution across primary and secondary stores |

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

During development and continuous evaluation, four significant failure patterns were identified and systematically resolved:

### 1. False PII Violations on Redacted Audit Logs (`has_pii`)
- **Failure**: Log parser extracted key-value pairs where values were literally `"null"` (e.g., `requester_name=null requester_email=null`). Standard string truthiness checks (`if val and val.strip()`) treated `"null"` as an active personal identifier, erroneously failing completed deletions.
- **Fix**: Enhanced `has_pii()` in `code/main.py` to filter out placeholder strings including `"null"`, `"none"`, `"nil"`, `"[redacted]"`, `"redacted"`, `"anonymized"`, and `"n/a"`.

### 2. Multi-Channel Historical Email Hash Tracing
- **Failure**: Historical identity resolution previously only checked current email addresses, missing resources stored under prior email hashes recorded in `user_audit_log.csv`.
- **Fix**: Expanded `build_identity_maps()` to index `user_to_hashes` and populate reverse maps across `hash_to_resources`. Updated `find_user_resources()` to search across all known past and present hashes.

### 3. Subject Access Request / Update Filtering (`is_deletion_requested`)
- **Failure**: Non-deletion communications (such as data export requests or profile address updates) were treated as deletion requests with partial failures.
- **Fix**: Introduced negative indicator heuristics and intent analysis in `is_deletion_requested()` to distinguish between Article 15 (SAR / Access) and Article 17 (Right to Erasure) requests, correctly yielding `NOT_APPLICABLE`.

### 4. Step Ordering and Verification Serialization
- **Failure**: Grader requires strict adherence to phase ordering (`FINDING` -> `REMEDIATION` -> `VERIFICATION`), internal operation sorting, and alphabetical sorting by `system_id` and `resource_id`.
- **Fix**: Centralized step sorting under `step_sort_key()` with explicit integer ranks for operations and re-indexing step numbers from 1 to N after phase assembly.

## Known Remaining Limitations

Although sample status accuracy is 100%, exact full-sequence accuracy is 7/32 (21.88%). Sequence mismatches remain unresolved. For example, case_31 predicted account_541 instead of account_4857, and case_32 predicted account_542 instead of account_8858. The improvements described above did not eliminate every sequence-level failure. The output has been structurally evaluated, but these results do not establish full correctness on the hidden benchmark.
