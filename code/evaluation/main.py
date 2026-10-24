#!/usr/bin/env python3
"""
Evaluation script for Ghost Data Still Exists.
Evaluates predictions against sample_output.csv, executes custom evaluation cases,
and verifies sequence and field-level accuracies.
"""

import sys
import json
import csv
from pathlib import Path

# Add code directory to path
CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))

from main import (
    load_csv,
    load_sample_requests,
    load_sample_output,
    load_user_identities,
    load_user_audit_log,
    load_system_activity,
    load_deletion_rules,
    load_evidence_files,
    build_identity_maps,
    EvidenceIndex,
    resolve_user,
    analyze_case,
    is_deletion_requested
)

def evaluate_samples():
    print("Loading datasets...")
    identities = load_user_identities()
    audit_log = load_user_audit_log()
    activities = load_system_activity()
    rules = load_deletion_rules()
    manifest = load_evidence_files()
    evidence_manifest_dict = {f["file_id"]: f for f in manifest}

    email_to_user, user_to_emails, user_to_info, user_to_phones, email_hash_to_user, name_to_user, user_to_hashes = build_identity_maps(
        identities, audit_log
    )

    print("Indexing evidence...")
    evidence_idx = EvidenceIndex(manifest)

    sample_requests = load_sample_requests()
    sample_output = load_sample_output()

    print(f"\nEvaluating {len(sample_requests)} sample requests...")

    correct_status = 0
    total_cases = len(sample_requests)
    
    mismatches = []
    
    total_expected_steps = 0
    total_predicted_steps = 0
    exact_step_matches = 0
    exact_sequence_matches = 0
    
    field_matches = {"phase": 0, "system_id": 0, "resource_id": 0, "operation": 0, "state": 0}
    total_fields = 0

    for case in sample_requests:
        case_id = case["case_id"]
        expected_row = sample_output.get(case_id)
        if not expected_row:
            continue
        
        expected_status = expected_row["deletion_status"]
        expected_steps = json.loads(expected_row["steps_json"])

        case_email = case["email"].strip().lower()
        user_id = resolve_user(case_email, email_to_user)
        emails = user_to_emails.get(user_id, set()) if user_id else {case_email}

        pred_status, pred_steps = analyze_case(
            case, user_id, emails, evidence_idx, evidence_manifest_dict,
            user_to_info, user_to_phones, email_hash_to_user, activities
        )

        clean_pred_steps = []
        for s in pred_steps:
            clean_pred_steps.append({
                "step_no": s["step_no"],
                "phase": s["phase"],
                "system_id": s["system_id"],
                "resource_id": s["resource_id"],
                "operation": s["operation"],
                "state": s["state"],
                "evidence_id": s["evidence_id"],
            })

        # Compare status
        if pred_status == expected_status:
            correct_status += 1
        else:
            mismatches.append({
                "case_id": case_id,
                "expected_status": expected_status,
                "pred_status": pred_status,
                "expected_steps_count": len(expected_steps),
                "pred_steps_count": len(clean_pred_steps)
            })

        # Compare steps and sequence
        total_expected_steps += len(expected_steps)
        total_predicted_steps += len(clean_pred_steps)

        case_sequence_match = (len(expected_steps) == len(clean_pred_steps))
        min_len = min(len(expected_steps), len(clean_pred_steps))
        
        for j in range(min_len):
            exp_s = expected_steps[j]
            prd_s = clean_pred_steps[j]
            step_match = True
            for field in ["phase", "system_id", "resource_id", "operation", "state"]:
                total_fields += 1
                if exp_s.get(field) == prd_s.get(field):
                    field_matches[field] += 1
                else:
                    step_match = False
            if step_match:
                exact_step_matches += 1
            else:
                case_sequence_match = False

        if case_sequence_match and len(expected_steps) > 0:
            exact_sequence_matches += 1

    status_acc = correct_status / total_cases * 100.0
    field_acc = {k: (v / (total_fields / 5) * 100.0) if total_fields > 0 else 0 for k, v in field_matches.items()}
    avg_field_acc = (sum(field_matches.values()) / total_fields * 100.0) if total_fields > 0 else 0.0
    seq_acc = exact_sequence_matches / total_cases * 100.0

    print(f"\n--- EVALUATION METRICS ON SAMPLE SET ---")
    print(f"Case-level Status Accuracy: {correct_status}/{total_cases} ({status_acc:.2f}%)")
    print(f"Total Expected Steps: {total_expected_steps}, Total Predicted: {total_predicted_steps}")
    print(f"Exact Step Matches: {exact_step_matches}")
    print(f"Full Sequence Accuracy: {exact_sequence_matches}/{total_cases} ({seq_acc:.2f}%)")
    print(f"Average Field Accuracy: {avg_field_acc:.2f}%")
    for fld, acc in field_acc.items():
        print(f"  Field '{fld}': {acc:.2f}%")

    if mismatches:
        print(f"\nStatus Mismatches ({len(mismatches)}):")
        for m in mismatches:
            print(f"  {m['case_id']}: expected {m['expected_status']}, got {m['pred_status']}")

    # Run Custom Cases
    print("\n--- RUNNING CUSTOM EVALUATION CASES ---")
    custom_results = run_custom_cases(evidence_idx, evidence_manifest_dict, user_to_info, user_to_phones, email_hash_to_user, activities, email_to_user, user_to_emails)

    return status_acc, avg_field_acc, seq_acc, custom_results


def run_custom_cases(evidence_idx, evidence_manifest_dict, user_to_info, user_to_phones, email_hash_to_user, activities, email_to_user, user_to_emails):
    """
    Three custom evaluation cases testing domain-specific edge cases:
    1. Custom Case 1: Non-deletion request (NOT_APPLICABLE). User requests data export without deletion.
    2. Custom Case 2: Historical email identity resolution finding active data flow.
    3. Custom Case 3: Retained tombstone validation ensuring PII redaction.
    """
    custom_cases = [
        {
            "case_id": "custom_case_01",
            "email": "export.request@example.com",
            "requested_at": "2026-09-01T10:00:00Z",
            "reported_status": "NOT_STARTED",
            "reported_at": "2026-09-01T12:00:00Z",
            "audit_at": "2026-09-05T12:00:00Z",
            "request_text": "Please send me a full copy of my purchase history for tax purposes. Do not close or delete my account as I use it frequently.",
            "expected_status": "NOT_APPLICABLE",
            "description": "Subject Access Request (SAR) explicitly requesting data export without deletion"
        },
        {
            "case_id": "custom_case_02",
            "email": "minjun.kim90@gmail.com", # Historical email of user_12
            "requested_at": "2026-09-10T12:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-09-12T12:00:00Z",
            "audit_at": "2026-09-15T12:00:00Z",
            "request_text": "I request complete deletion of all records associated with my old email address.",
            "expected_status": "INCOMPLETE",
            "description": "Historical email audit detecting remaining analytics profile (analytics_9914)"
        },
        {
            "case_id": "custom_case_03",
            "email": "charlotte.wright@outlook.com", # case_01 user
            "requested_at": "2026-07-16T08:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-07-18T02:00:00Z",
            "audit_at": "2026-09-26T12:00:00Z",
            "request_text": "Please delete my account and ensure personal identifiers are removed.",
            "expected_status": "COMPLETE",
            "description": "Verification of complete deletion with verification steps cited"
        }
    ]

    results = []
    for c in custom_cases:
        cid = c["case_id"]
        c_email = c["email"].strip().lower()
        uid = resolve_user(c_email, email_to_user)
        em_set = user_to_emails.get(uid, set()) if uid else {c_email}

        status, steps = analyze_case(
            c, uid, em_set, evidence_idx, evidence_manifest_dict,
            user_to_info, user_to_phones, email_hash_to_user, activities
        )

        passed = (status == c["expected_status"])
        print(f"  [{'PASS' if passed else 'FAIL'}] {cid}: {c['description']}")
        print(f"         Expected: {c['expected_status']}, Got: {status}, Steps Count: {len(steps)}")
        results.append({
            "case_id": cid,
            "description": c["description"],
            "expected": c["expected_status"],
            "actual": status,
            "passed": passed,
            "steps": steps
        })

    return results

if __name__ == "__main__":
    evaluate_samples()
