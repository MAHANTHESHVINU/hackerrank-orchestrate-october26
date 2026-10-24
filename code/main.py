#!/usr/bin/env python3
"""
Ghost Data Still Exists — HackerRank Orchestrate October 2026
Deterministic deletion-audit agent.

Reads dataset/, resolves identities, searches evidence, applies deletion_rules,
and writes output.csv with case_id, deletion_status, steps_json.
"""

import csv
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "dataset"
EVIDENCE_DIR = DATASET_DIR / "evidence"
OUTPUT_PATH = BASE_DIR / "output.csv"

# ---------------------------------------------------------------------------
# 1. Load CSVs
# ---------------------------------------------------------------------------

def load_csv(name):
    """Load a CSV from dataset/ and return list of dicts."""
    path = DATASET_DIR / name
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_deletion_requests():
    return load_csv("deletion_requests.csv")


def load_sample_requests():
    return load_csv("sample_deletion_requests.csv")


def load_sample_output():
    rows = []
    path = DATASET_DIR / "sample_output.csv"
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return {r["case_id"]: r for r in rows}


def load_user_identities():
    return load_csv("user_identities.csv")


def load_user_audit_log():
    return load_csv("user_audit_log.csv")


def load_system_activity():
    return load_csv("system_activity.csv")


def load_deletion_rules():
    return load_csv("deletion_rules.csv")


def load_evidence_files():
    return load_csv("evidence_files.csv")


# ---------------------------------------------------------------------------
# 2. Identity resolution
# ---------------------------------------------------------------------------

def build_identity_maps(identities, audit_log):
    """
    Build:
      - email_to_user: email (lowered) -> user_id
      - user_to_emails: user_id -> set of all emails (current + historical)
      - user_to_info: user_id -> dict of current identity fields
      - user_to_phones: user_id -> set of all phones (current + historical)
      - email_hash_to_user: hash -> user_id
    """
    email_to_user = {}
    user_to_emails = defaultdict(set)
    user_to_info = {}
    user_to_phones = defaultdict(set)
    email_hash_to_user = {}
    user_to_hashes = defaultdict(set)
    name_to_user = defaultdict(set)

    for u in identities:
        uid = u["user_id"]
        email = u["email"].strip().lower()
        email_to_user[email] = uid
        user_to_emails[uid].add(email)
        user_to_info[uid] = u
        if u.get("phone"):
            user_to_phones[uid].add(u["phone"].strip())
        if u.get("email_hash"):
            h = u["email_hash"].strip()
            email_hash_to_user[h] = uid
            user_to_hashes[uid].add(h)
        if u.get("name"):
            name_to_user[u["name"].strip().lower()].add(uid)

    # Add historical emails/phones/hashes from audit log
    for entry in audit_log:
        uid = entry["user_id"]
        field = entry["field_name"]
        if field == "email":
            if entry.get("old_value"):
                old_email = entry["old_value"].strip().lower()
                user_to_emails[uid].add(old_email)
                email_to_user[old_email] = uid
            if entry.get("new_value"):
                new_email = entry["new_value"].strip().lower()
                user_to_emails[uid].add(new_email)
                email_to_user[new_email] = uid
        elif field == "phone":
            if entry.get("old_value"):
                user_to_phones[uid].add(entry["old_value"].strip())
            if entry.get("new_value"):
                user_to_phones[uid].add(entry["new_value"].strip())
        elif field == "email_hash":
            if entry.get("old_value"):
                old_h = entry["old_value"].strip()
                email_hash_to_user[old_h] = uid
                user_to_hashes[uid].add(old_h)
            if entry.get("new_value"):
                new_h = entry["new_value"].strip()
                email_hash_to_user[new_h] = uid
                user_to_hashes[uid].add(new_h)
        elif field == "name":
            if entry.get("old_value"):
                name_to_user[entry["old_value"].strip().lower()].add(uid)
            if entry.get("new_value"):
                name_to_user[entry["new_value"].strip().lower()].add(uid)

    return email_to_user, user_to_emails, user_to_info, user_to_phones, email_hash_to_user, name_to_user, user_to_hashes


def resolve_user(email, email_to_user):
    """Resolve a case email to a user_id."""
    return email_to_user.get(email.strip().lower())


# ---------------------------------------------------------------------------
# 3. Evidence loading and indexing
# ---------------------------------------------------------------------------

def load_json_evidence(file_path):
    """Load a JSON evidence file."""
    full_path = DATASET_DIR / file_path
    if not full_path.exists():
        return None
    with open(full_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_sql_evidence(file_path):
    """Execute a SQL evidence file in SQLite and return tables as dicts."""
    full_path = DATASET_DIR / file_path
    if not full_path.exists():
        return {}
    
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        sql_text = full_path.read_text(encoding="utf-8")
        conn.executescript(sql_text)
    except Exception:
        conn.close()
        return {}
    
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    result = {}
    for table in tables:
        cursor.execute(f'SELECT * FROM "{table}"')
        cols = [desc[0] for desc in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        result[table] = rows
    
    conn.close()
    return result


def load_log_evidence(file_path):
    """Load a log evidence file and return lines."""
    full_path = DATASET_DIR / file_path
    if not full_path.exists():
        return []
    with open(full_path, "r", encoding="utf-8") as f:
        return f.readlines()


def load_text_evidence(file_path):
    """Load a text evidence file."""
    full_path = DATASET_DIR / file_path
    if not full_path.exists():
        return ""
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# 4. Build a comprehensive resource index from all evidence
# ---------------------------------------------------------------------------

class EvidenceIndex:
    """Indexes all evidence files into searchable structures keyed by user identifiers."""
    
    def __init__(self, evidence_manifest):
        self.manifest = {e["file_id"]: e for e in evidence_manifest}
        
        # resource_id -> list of (file_id, system_id, record_data)
        self.account_records = {}       # resource_id -> (file_id, record)
        self.search_records = {}        # resource_id -> (file_id, record)
        self.analytics_records = {}     # resource_id -> (file_id, record)
        self.support_records = {}       # resource_id -> (file_id, record)
        self.export_records = {}        # resource_id -> (file_id, record)
        self.backup_records = {}        # resource_id -> (file_id, record)
        self.security_records = {}      # resource_id -> (file_id, record)
        self.data_flow_records = {}     # resource_id -> (file_id, record)
        self.tombstone_records = {}     # resource_id -> (file_id, record)
        self.email_delivery_records = {} # resource_id -> (file_id, record)
        self.marketing_records = {}     # resource_id -> (file_id, record)
        
        # Maps: email (lowered) -> set of resource_ids per system
        self.email_to_accounts = defaultdict(set)
        self.email_to_search = defaultdict(set)
        self.email_to_analytics = defaultdict(set)
        self.email_to_support = defaultdict(set)
        self.email_to_exports = defaultdict(set)
        self.email_to_backups = defaultdict(set)
        self.email_to_security = defaultdict(set)
        self.email_to_data_flows = defaultdict(set)
        self.email_to_tombstones = defaultdict(set)
        self.email_to_marketing = defaultdict(set)
        
        # Maps: user_id -> set of resource_ids per system
        self.user_to_accounts = defaultdict(set)
        self.user_to_search = defaultdict(set)
        self.user_to_analytics = defaultdict(set)
        self.user_to_support = defaultdict(set)
        self.user_to_exports = defaultdict(set)
        self.user_to_backups = defaultdict(set)
        self.user_to_security = defaultdict(set)
        self.user_to_data_flows = defaultdict(set)
        self.user_to_tombstones = defaultdict(set)
        self.user_to_marketing = defaultdict(set)
        
        # email_hash -> resource_ids
        self.hash_to_resources = defaultdict(set)
        
        # phone -> resource_ids
        self.phone_to_resources = defaultdict(set)
        
        # name (lowered) -> resource_ids
        self.name_to_resources = defaultdict(set)
        
        self._load_all()
    
    def _load_all(self):
        for file_id, meta in self.manifest.items():
            file_path = meta["file_path"]
            
            if file_path.endswith(".json"):
                self._index_json(file_id, file_path)
            elif file_path.endswith(".sql"):
                self._index_sql(file_id, file_path)
            elif file_path.endswith(".log"):
                self._index_log(file_id, file_path)
            elif file_path.endswith(".txt"):
                self._index_text(file_id, file_path)
            elif file_path.endswith(".pdf"):
                self._index_pdf(file_id, file_path)
    
    def _index_json(self, file_id, file_path):
        data = load_json_evidence(file_path)
        if not data:
            return
        
        # Handle service_resource_export files
        if "service_exports" in data:
            exports = data["service_exports"]
            self._index_service_exports(file_id, exports)
            return
        
        # Handle customer_data_snapshot_bundle files
        if "snapshots" in data or "snapshot_bundles" in data or "records" in data:
            self._index_snapshot_bundle(file_id, data)
            return
        
        # Handle customer_analytics_report
        if "analytics_profiles" in data or "profiles" in data:
            self._index_analytics_report(file_id, data)
            return
        
        # Handle customer_export_jobs
        if "export_jobs" in data or "exports" in data:
            self._index_export_jobs(file_id, data)
            return
        
        # Handle connector_configurations
        if "connectors" in data or "configurations" in data:
            self._index_connectors(file_id, data)
            return
        
        # Handle security_audit_ledger
        if "audit_entries" in data or "audit_records" in data:
            self._index_security_ledger(file_id, data)
            return
        
        # Handle customer_export_manifest
        if "manifest" in data or "customer_exports" in data:
            self._index_export_manifest(file_id, data)
            return
        
        # Generic: try to walk through all nested structures
        self._index_generic_json(file_id, data)
    
    def _index_service_exports(self, file_id, exports):
        """Index service_resource_export JSON files."""
        # account_service
        if "account_service" in exports:
            acct_svc = exports["account_service"]
            for lookup_key in ["profile_lookups", "profiles", "accounts"]:
                for rec in acct_svc.get(lookup_key, []):
                    rid = rec.get("resource_id")
                    if not rid:
                        continue
                    self.account_records[rid] = (file_id, rec)
                    email = (rec.get("email") or rec.get("profile", {}) or {}).get("email") if isinstance(rec.get("profile"), dict) else rec.get("email")
                    if isinstance(rec.get("profile"), dict):
                        profile = rec["profile"]
                        if profile:
                            email = email or profile.get("email")
                            if profile.get("email_hash"):
                                self.hash_to_resources[profile["email_hash"]].add(rid)
                            if profile.get("full_name"):
                                self.name_to_resources[profile["full_name"].lower()].add(rid)
                            if profile.get("phone"):
                                self.phone_to_resources[profile["phone"]].add(rid)
                    if email:
                        self.email_to_accounts[email.lower()].add(rid)
                    cref = rec.get("customer_reference") or (rec.get("profile") or {}).get("customer_reference") if isinstance(rec.get("profile"), dict) else rec.get("customer_reference")
                    if cref:
                        self.user_to_accounts[cref].add(rid)
                    # 404 means absent
                    if rec.get("status_code") == 404:
                        rec["_absent"] = True
        
        # search_service
        if "search_service" in exports:
            search_svc = exports["search_service"]
            for query_key in ["index_queries", "queries", "entries"]:
                for rec in search_svc.get(query_key, []):
                    rid = rec.get("resource_id")
                    if not rid:
                        continue
                    self.search_records[rid] = (file_id, rec)
                    # Extract email from hits
                    hits = rec.get("hits", {})
                    docs = hits.get("documents", [])
                    for doc in docs:
                        email = doc.get("email")
                        if email:
                            self.email_to_search[email.lower()].add(rid)
                        if doc.get("customer_reference"):
                            self.user_to_search[doc["customer_reference"]].add(rid)
                        if doc.get("email_hash"):
                            self.hash_to_resources[doc["email_hash"]].add(rid)
                        if doc.get("phone"):
                            self.phone_to_resources[doc["phone"]].add(rid)
                        if doc.get("display_name"):
                            self.name_to_resources[doc["display_name"].lower()].add(rid)
                    # Also check query field
                    query = rec.get("query", "")
                    if "@" in query:
                        self.email_to_search[query.lower()].add(rid)
        
        # analytics_platform
        if "analytics_platform" in exports:
            analytics = exports["analytics_platform"]
            for key in ["profiles", "entries", "records"]:
                for rec in analytics.get(key, []):
                    rid = rec.get("resource_id")
                    if not rid:
                        continue
                    self.analytics_records[rid] = (file_id, rec)
                    email = rec.get("email")
                    if email:
                        self.email_to_analytics[email.lower()].add(rid)
                    cref = rec.get("customer_reference")
                    if cref:
                        self.user_to_analytics[cref].add(rid)
                    if rec.get("email_hash"):
                        self.hash_to_resources[rec["email_hash"]].add(rid)
                    if rec.get("phone"):
                        self.phone_to_resources[rec["phone"]].add(rid)
        
        # support_platform
        if "support_platform" in exports:
            support = exports["support_platform"]
            for key in ["tickets", "cases", "entries"]:
                for rec in support.get(key, []):
                    rid = rec.get("resource_id")
                    if not rid:
                        continue
                    self.support_records[rid] = (file_id, rec)
                    email = rec.get("requester_email")
                    if email:
                        self.email_to_support[email.lower()].add(rid)
                    cref = rec.get("customer_reference")
                    if cref:
                        self.user_to_support[cref].add(rid)
                    if rec.get("requester_phone"):
                        self.phone_to_resources[rec["requester_phone"]].add(rid)
                    if rec.get("requester_name"):
                        self.name_to_resources[rec["requester_name"].lower()].add(rid)
        
        # export_service
        if "export_service" in exports:
            export_svc = exports["export_service"]
            for key in ["exports", "jobs", "entries"]:
                for rec in export_svc.get(key, []):
                    rid = rec.get("resource_id")
                    if not rid:
                        continue
                    self.export_records[rid] = (file_id, rec)
                    email = rec.get("owner_email")
                    if email:
                        self.email_to_exports[email.lower()].add(rid)
                    cref = rec.get("customer_reference")
                    if cref:
                        self.user_to_exports[cref].add(rid)
        
        # backup_service
        if "backup_service" in exports:
            backup_svc = exports["backup_service"]
            for key in ["restore_entries", "backups", "entries"]:
                for rec in backup_svc.get(key, []):
                    rid = rec.get("resource_id")
                    if not rid:
                        continue
                    self.backup_records[rid] = (file_id, rec)
                    email = rec.get("customer_email")
                    if email:
                        self.email_to_accounts[email.lower()].add(rid)
                    cref = rec.get("customer_reference")
                    if cref:
                        self.user_to_backups[cref].add(rid)
        
        # security_service
        if "security_service" in exports:
            sec_svc = exports["security_service"]
            for key in ["audit_records", "entries", "records"]:
                for rec in sec_svc.get(key, []):
                    rid = rec.get("resource_id")
                    if not rid:
                        continue
                    self.security_records[rid] = (file_id, rec)
                    cref = rec.get("subject_reference")
                    if cref:
                        self.user_to_security[cref].add(rid)
        
        # integration_service
        if "integration_service" in exports:
            int_svc = exports["integration_service"]
            for key in ["connectors", "data_flows", "entries"]:
                for rec in int_svc.get(key, []):
                    rid = rec.get("resource_id")
                    if not rid:
                        continue
                    self.data_flow_records[rid] = (file_id, rec)
                    email = rec.get("customer_email")
                    if email:
                        self.email_to_data_flows[email.lower()].add(rid)
                    cref = rec.get("customer_reference")
                    if cref:
                        self.user_to_data_flows[cref].add(rid)
        
        # identity_service (tombstones)
        if "identity_service" in exports:
            id_svc = exports["identity_service"]
            for key in ["tombstones", "records", "entries"]:
                for rec in id_svc.get(key, []):
                    rid = rec.get("resource_id")
                    if not rid:
                        continue
                    self.tombstone_records[rid] = (file_id, rec)
                    cref = rec.get("customer_reference") or rec.get("user_reference")
                    if cref:
                        self.user_to_tombstones[cref].add(rid)
                    email = rec.get("email")
                    if email:
                        self.email_to_tombstones[email.lower()].add(rid)
                    if rec.get("email_hash"):
                        self.hash_to_resources[rec["email_hash"]].add(rid)
                    if rec.get("phone"):
                        self.phone_to_resources[rec["phone"]].add(rid)
                    if rec.get("full_name"):
                        self.name_to_resources[rec["full_name"].lower()].add(rid)
        
        # marketing_platform
        if "marketing_platform" in exports:
            mkt = exports["marketing_platform"]
            for key in ["profiles", "entries", "records"]:
                for rec in mkt.get(key, []):
                    rid = rec.get("resource_id")
                    if not rid:
                        continue
                    self.marketing_records[rid] = (file_id, rec)
                    email = rec.get("email")
                    if email:
                        self.email_to_marketing[email.lower()].add(rid)
                    cref = rec.get("customer_reference")
                    if cref:
                        self.user_to_marketing[cref].add(rid)
    
    def _index_snapshot_bundle(self, file_id, data):
        """Index customer_data_snapshot_bundle JSON files."""
        # These can have various structures - handle generically
        self._walk_and_index(file_id, data)
    
    def _index_analytics_report(self, file_id, data):
        """Index analytics report JSON."""
        for key in ["analytics_profiles", "profiles"]:
            for rec in data.get(key, []):
                rid = rec.get("resource_id")
                if not rid:
                    continue
                self.analytics_records[rid] = (file_id, rec)
                email = rec.get("email")
                if email:
                    self.email_to_analytics[email.lower()].add(rid)
                cref = rec.get("customer_reference") or rec.get("user_id")
                if cref:
                    self.user_to_analytics[cref].add(rid)
    
    def _index_export_jobs(self, file_id, data):
        """Index export jobs JSON."""
        for key in ["export_jobs", "exports"]:
            for rec in data.get(key, []):
                rid = rec.get("resource_id")
                if not rid:
                    continue
                self.export_records[rid] = (file_id, rec)
                email = rec.get("owner_email") or rec.get("email")
                if email:
                    self.email_to_exports[email.lower()].add(rid)
                cref = rec.get("customer_reference") or rec.get("user_id")
                if cref:
                    self.user_to_exports[cref].add(rid)
    
    def _index_connectors(self, file_id, data):
        """Index connector configuration JSON."""
        for key in ["connectors", "configurations"]:
            for rec in data.get(key, []):
                rid = rec.get("resource_id")
                if not rid:
                    continue
                self.data_flow_records[rid] = (file_id, rec)
                email = rec.get("customer_email")
                if email:
                    self.email_to_data_flows[email.lower()].add(rid)
                cref = rec.get("customer_reference")
                if cref:
                    self.user_to_data_flows[cref].add(rid)
    
    def _index_security_ledger(self, file_id, data):
        """Index security audit ledger JSON."""
        for key in ["audit_entries", "audit_records"]:
            for rec in data.get(key, []):
                rid = rec.get("resource_id")
                if not rid:
                    continue
                self.security_records[rid] = (file_id, rec)
                cref = rec.get("subject_reference")
                if cref:
                    self.user_to_security[cref].add(rid)
    
    def _index_export_manifest(self, file_id, data):
        """Index customer export manifest JSON."""
        for key in ["manifest", "customer_exports"]:
            items = data.get(key, [])
            if isinstance(items, dict):
                items = list(items.values()) if all(isinstance(v, dict) for v in items.values()) else [items]
            for rec in items:
                if not isinstance(rec, dict):
                    continue
                rid = rec.get("resource_id")
                if not rid:
                    continue
                self.export_records[rid] = (file_id, rec)
                email = rec.get("owner_email") or rec.get("email")
                if email:
                    self.email_to_exports[email.lower()].add(rid)
                cref = rec.get("customer_reference") or rec.get("user_id")
                if cref:
                    self.user_to_exports[cref].add(rid)
    
    def _index_generic_json(self, file_id, data):
        """Walk any JSON and index records with resource_id."""
        self._walk_and_index(file_id, data)
    
    def _walk_and_index(self, file_id, obj, depth=0):
        if depth > 10:
            return
        if isinstance(obj, dict):
            rid = obj.get("resource_id")
            if rid:
                # Determine system from resource prefix
                self._classify_and_store(file_id, rid, obj)
            for v in obj.values():
                self._walk_and_index(file_id, v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                self._walk_and_index(file_id, item, depth + 1)
    
    def _classify_and_store(self, file_id, rid, rec):
        """Classify a record by its resource_id prefix and store it."""
        email = None
        cref = None
        
        # Extract identifiers generically
        for email_key in ["email", "owner_email", "requester_email", "customer_email"]:
            if rec.get(email_key):
                email = rec[email_key]
                break
        for ref_key in ["customer_reference", "user_reference", "subject_reference", "user_id"]:
            if rec.get(ref_key):
                cref = rec[ref_key]
                break
        
        if rid.startswith("account_"):
            self.account_records[rid] = (file_id, rec)
            if email:
                self.email_to_accounts[email.lower()].add(rid)
            if cref:
                self.user_to_accounts[cref].add(rid)
        elif rid.startswith("search_"):
            self.search_records[rid] = (file_id, rec)
            if email:
                self.email_to_search[email.lower()].add(rid)
            if cref:
                self.user_to_search[cref].add(rid)
        elif rid.startswith("analytics_"):
            self.analytics_records[rid] = (file_id, rec)
            if email:
                self.email_to_analytics[email.lower()].add(rid)
            if cref:
                self.user_to_analytics[cref].add(rid)
        elif rid.startswith("support_"):
            self.support_records[rid] = (file_id, rec)
            if email:
                self.email_to_support[email.lower()].add(rid)
            if cref:
                self.user_to_support[cref].add(rid)
        elif rid.startswith("export_"):
            self.export_records[rid] = (file_id, rec)
            if email:
                self.email_to_exports[email.lower()].add(rid)
            if cref:
                self.user_to_exports[cref].add(rid)
        elif rid.startswith("backup_"):
            self.backup_records[rid] = (file_id, rec)
            if cref:
                self.user_to_backups[cref].add(rid)
            if email:
                self.email_to_backups[email.lower()].add(rid)
        elif rid.startswith("audit_record_"):
            self.security_records[rid] = (file_id, rec)
            if cref:
                self.user_to_security[cref].add(rid)
            if email:
                self.email_to_security[email.lower()].add(rid)
        elif rid.startswith("data_flow_"):
            self.data_flow_records[rid] = (file_id, rec)
            if email:
                self.email_to_data_flows[email.lower()].add(rid)
            if cref:
                self.user_to_data_flows[cref].add(rid)
        elif rid.startswith("tombstone_"):
            self.tombstone_records[rid] = (file_id, rec)
            if email:
                self.email_to_tombstones[email.lower()].add(rid)
            if cref:
                self.user_to_tombstones[cref].add(rid)
        elif rid.startswith("marketing_"):
            self.marketing_records[rid] = (file_id, rec)
            if email:
                self.email_to_marketing[email.lower()].add(rid)
            if cref:
                self.user_to_marketing[cref].add(rid)
    
    def _index_sql(self, file_id, file_path):
        """Index SQL evidence files, including embedded JSON payloads."""
        tables = load_sql_evidence(file_path)
        for table_name, rows in tables.items():
            for row in rows:
                rid = row.get("resource_id")
                # Look for embedded JSON strings in row values (e.g. record_json)
                for col_val in list(row.values()):
                    if isinstance(col_val, str) and col_val.strip().startswith("{") and col_val.strip().endswith("}"):
                        try:
                            parsed_json = json.loads(col_val)
                            if isinstance(parsed_json, dict):
                                for k, v in parsed_json.items():
                                    if k not in row or not row[k]:
                                        row[k] = v
                                    if k == "resource_id" and not rid:
                                        rid = v
                                    if k == "document" and isinstance(v, dict):
                                        for dk, dv in v.items():
                                            if dk not in row or not row[dk]:
                                                row[dk] = dv
                        except Exception:
                            pass
                
                if not rid:
                    continue
                
                email = row.get("email") or row.get("customer_email") or row.get("owner_email") or row.get("requester_email")
                user_id = row.get("user_id") or row.get("customer_reference") or row.get("user_reference") or row.get("subject_reference")
                
                self._classify_and_store(file_id, rid, row)
                
                if email:
                    email_low = email.lower()
                    if rid.startswith("account_"):
                        self.email_to_accounts[email_low].add(rid)
                    elif rid.startswith("search_"):
                        self.email_to_search[email_low].add(rid)
                    elif rid.startswith("analytics_"):
                        self.email_to_analytics[email_low].add(rid)
                    elif rid.startswith("support_"):
                        self.email_to_support[email_low].add(rid)
                    elif rid.startswith("export_"):
                        self.email_to_exports[email_low].add(rid)
                    elif rid.startswith("backup_"):
                        self.email_to_backups[email_low].add(rid)
                    elif rid.startswith("audit_record_"):
                        self.email_to_security[email_low].add(rid)
                    elif rid.startswith("data_flow_"):
                        self.email_to_data_flows[email_low].add(rid)
                
                if user_id:
                    if rid.startswith("account_"):
                        self.user_to_accounts[user_id].add(rid)
                    elif rid.startswith("search_"):
                        self.user_to_search[user_id].add(rid)
                    elif rid.startswith("analytics_"):
                        self.user_to_analytics[user_id].add(rid)
                    elif rid.startswith("support_"):
                        self.user_to_support[user_id].add(rid)
                    elif rid.startswith("export_"):
                        self.user_to_exports[user_id].add(rid)
                    elif rid.startswith("backup_"):
                        self.user_to_backups[user_id].add(rid)
                    elif rid.startswith("audit_record_"):
                        self.user_to_security[user_id].add(rid)
                    elif rid.startswith("data_flow_"):
                        self.user_to_data_flows[user_id].add(rid)
                
                if row.get("full_name") or row.get("display_name"):
                    fn = row.get("full_name") or row.get("display_name")
                    self.name_to_resources[fn.lower()].add(rid)
                if row.get("phone"):
                    self.phone_to_resources[row["phone"]].add(rid)
                if row.get("email_hash"):
                    self.hash_to_resources[row["email_hash"]].add(rid)
    
    def _index_log(self, file_id, file_path):
        """Index log evidence files with structured key-value parsing and trace grouping."""
        lines = load_log_evidence(file_path)
        traces = defaultdict(dict)
        
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            
            # Parse key=value pairs
            kv = {}
            for match in re.finditer(r'(\w+)=(?:"([^"]*)"|([^\s]+))', line_str):
                k = match.group(1)
                v = match.group(2) if match.group(2) is not None else match.group(3)
                kv[k] = v
            
            trace_id = kv.get("trace_id")
            if trace_id:
                traces[trace_id].update(kv)
            
            # Extract resource IDs
            resource_matches = re.findall(
                r'(account_\d+|search_\d+|analytics_\d+|support_\d+|export_\d+|'
                r'backup_\d+|audit_record_\d+|data_flow_\d+|tombstone_\d+|'
                r'marketing_\d+|email_delivery_\d+)',
                line_str
            )
            
            email_matches = re.findall(r'[\w.+-]+@[\w.-]+\.\w+', line_str)
            user_matches = re.findall(r'user_\d+', line_str)
            
            for rid in resource_matches:
                rec = dict(kv)
                rec["resource_id"] = rid
                rec["_log_line"] = line_str
                rec["_log_file"] = file_path
                
                # Check trace context
                if trace_id and trace_id in traces:
                    rec.update(traces[trace_id])
                
                # Check lookup_key or correlation_key
                lookup = rec.get("lookup_key") or rec.get("subject_key") or rec.get("correlation_key")
                if lookup and lookup != "null":
                    if "@" in lookup:
                        rec["email"] = lookup
                    elif lookup.startswith("user_"):
                        rec["user_reference"] = lookup
                    elif len(lookup) == 64:
                        rec["email_hash"] = lookup
                        self.hash_to_resources[lookup].add(rid)
                
                # Check restore candidate evaluation or connector heartbeat flags
                if rec.get("eligible") == "true" and rec.get("deletion_block") == "false":
                    rec["restore_allowed"] = True
                if rec.get("eligible") == "true" and rec.get("deletion_block") == "true":
                    rec["restore_allowed"] = False
                
                for em in email_matches:
                    rec["email"] = em
                for uid in user_matches:
                    rec["user_reference"] = uid
                
                # Detect absence (404 / 0 rows)
                if rec.get("rows") in ("0", 0) or rec.get("http_status") in ("404", 404) or rec.get("marker_found") == "false":
                    rec["_absent"] = True
                
                # Check restore_allowed boolean
                if "restore_allowed" in rec:
                    val = str(rec["restore_allowed"]).lower()
                    rec["restore_allowed"] = (val in ("true", "1"))
                
                # Check enabled boolean
                if "enabled" in rec:
                    val = str(rec["enabled"]).lower()
                    rec["enabled"] = (val in ("true", "1"))
                
                self._classify_and_store(file_id, rid, rec)

    def _index_pdf(self, file_id, file_path):
        """Index PDF evidence files using pypdf."""
        if not PdfReader:
            return
        full_path = DATASET_DIR / file_path
        if not full_path.exists():
            return
        try:
            reader = PdfReader(str(full_path))
            for page in reader.pages:
                text = page.extract_text()
                if not text:
                    continue
                resource_matches = re.findall(
                    r'(account_\d+|search_\d+|analytics_\d+|support_\d+|export_\d+|'
                    r'backup_\d+|audit_record_\d+|data_flow_\d+|tombstone_\d+|'
                    r'marketing_\d+)',
                    text
                )
                email_matches = re.findall(r'[\w.+-]+@[\w.-]+\.\w+', text)
                user_matches = re.findall(r'user_\d+', text)
                for rid in resource_matches:
                    rec = {"resource_id": rid, "_pdf_file": file_path}
                    for em in email_matches:
                        rec["email"] = em
                    for uid in user_matches:
                        rec["user_reference"] = uid
                    self._classify_and_store(file_id, rid, rec)
        except Exception:
            pass

    def _index_text(self, file_id, file_path):
        """Index text evidence files."""
        text = load_text_evidence(file_path)
        if not text:
            return
        
        for line in text.split("\n"):
            resource_matches = re.findall(
                r'(account_\d+|search_\d+|analytics_\d+|support_\d+|export_\d+|'
                r'backup_\d+|audit_record_\d+|data_flow_\d+|tombstone_\d+|'
                r'marketing_\d+)',
                line
            )
            email_matches = re.findall(r'[\w.+-]+@[\w.-]+\.\w+', line)
            user_matches = re.findall(r'user_\d+', line)
            
            for rid in resource_matches:
                rec = {"resource_id": rid, "_text_line": line.strip()}
                for em in email_matches:
                    rec["email"] = em
                for uid in user_matches:
                    rec["user_reference"] = uid
                self._classify_and_store(file_id, rid, rec)


# ---------------------------------------------------------------------------
# 5. Resource state assessment
# ---------------------------------------------------------------------------

def is_record_absent(rec):
    """Check if a record indicates absence (404, deleted, etc.)."""
    if rec.get("_absent"):
        return True
    if rec.get("status_code") == 404 or rec.get("http_status") in ("404", 404) or rec.get("rows") in ("0", 0):
        return True
    if rec.get("account_status") in ("DELETED", "CLOSED"):
        return True
    return False


def has_pii(rec):
    """Check if a record still contains PII (email, name, phone, email_hash)."""
    profile = rec.get("profile", {}) if isinstance(rec.get("profile"), dict) else {}
    
    pii_fields = ["email", "full_name", "phone", "email_hash",
                   "requester_email", "requester_name", "requester_phone",
                   "owner_email", "customer_email", "display_name"]
    
    for field in pii_fields:
        val = rec.get(field) or profile.get(field)
        if val is not None:
            val_str = str(val).strip().lower()
            if val_str and val_str not in ("null", "none", "nil", "undefined", "[redacted]", "redacted", "anonymized", "n/a", "{}"):
                return True
    return False


def is_data_flow_active(rec):
    """Check if a data flow / connector is active."""
    if rec.get("enabled") is True:
        return True
    if rec.get("last_delivery_status") in ("delivered", "active"):
        return True
    return False


def is_restore_allowed(rec):
    """Check if a backup restore is allowed."""
    if rec.get("restore_allowed") is True:
        return True
    if rec.get("restore_allowed") is False:
        return False
    return True  # Default: assume allowed unless explicitly blocked


def is_record_anonymized(rec):
    """Check if an analytics record is properly anonymized (no PII)."""
    return not has_pii(rec)


def is_tombstone_properly_redacted(rec):
    """Check if a tombstone only has user_id reference and no PII."""
    # A tombstone is properly redacted if it has no email, name, phone, hash
    return not has_pii(rec)


# ---------------------------------------------------------------------------
# 6. Case analysis
# ---------------------------------------------------------------------------

def is_deletion_requested(request_text):
    """Determine if the request_text actually requests deletion."""
    if not request_text:
        return True
    
    text_lower = request_text.lower()
    
    # Explicit negative indicators (asking not to delete or asking to leave intact)
    negative_indicators = [
        "don't delete", "dont delete", "do not delete", "not delete",
        "don't close", "dont close", "do not close", "not close",
        "continue using", "leave my", "intact", "without deleting",
        "don't change anything", "dont change anything", "do not change anything"
    ]
    for neg in negative_indicators:
        if neg in text_lower:
            return False
            
    # Check for requests that are only for email address change or data export without deletion
    if "change the email" in text_lower or "update my email" in text_lower or "change my email" in text_lower:
        if not any(k in text_lower for k in ["delet", "eras", "close", "supprimer", "eliminar", "löschen", "exclusão"]):
            return False
            
    if ("send me a copy" in text_lower or "copy of the information" in text_lower or "export my data" in text_lower or "copy of my" in text_lower) and not any(k in text_lower for k in ["delet", "eras", "close", "supprimer", "eliminar", "löschen", "exclusão"]):
        return False
        
    return True


def find_user_resources(user_id, emails, evidence_idx, user_to_info, user_to_phones, email_hash_to_user):
    """Find all resources belonging to a user across all systems."""
    resources = {
        "account": set(),
        "search": set(),
        "analytics": set(),
        "support": set(),
        "export": set(),
        "backup": set(),
        "security": set(),
        "data_flow": set(),
        "tombstone": set(),
        "marketing": set(),
    }
    
    # Search by user_id
    if user_id:
        resources["account"].update(evidence_idx.user_to_accounts.get(user_id, set()))
        resources["search"].update(evidence_idx.user_to_search.get(user_id, set()))
        resources["analytics"].update(evidence_idx.user_to_analytics.get(user_id, set()))
        resources["support"].update(evidence_idx.user_to_support.get(user_id, set()))
        resources["export"].update(evidence_idx.user_to_exports.get(user_id, set()))
        resources["backup"].update(evidence_idx.user_to_backups.get(user_id, set()))
        resources["security"].update(evidence_idx.user_to_security.get(user_id, set()))
        resources["data_flow"].update(evidence_idx.user_to_data_flows.get(user_id, set()))
        resources["tombstone"].update(evidence_idx.user_to_tombstones.get(user_id, set()))
        resources["marketing"].update(evidence_idx.user_to_marketing.get(user_id, set()))
    
    # Search by all known emails
    for email in emails:
        email_low = email.lower()
        resources["account"].update(evidence_idx.email_to_accounts.get(email_low, set()))
        resources["search"].update(evidence_idx.email_to_search.get(email_low, set()))
        resources["analytics"].update(evidence_idx.email_to_analytics.get(email_low, set()))
        resources["support"].update(evidence_idx.email_to_support.get(email_low, set()))
        resources["export"].update(evidence_idx.email_to_exports.get(email_low, set()))
        resources["backup"].update(evidence_idx.email_to_backups.get(email_low, set()))
        resources["security"].update(evidence_idx.email_to_security.get(email_low, set()))
        resources["data_flow"].update(evidence_idx.email_to_data_flows.get(email_low, set()))
        resources["tombstone"].update(evidence_idx.email_to_tombstones.get(email_low, set()))
        resources["marketing"].update(evidence_idx.email_to_marketing.get(email_low, set()))
    
    # Search by email hash (current + historical)
    hashes_to_check = set()
    if user_id and user_id in user_to_info:
        info = user_to_info[user_id]
        if info.get("email_hash"):
            hashes_to_check.add(info["email_hash"].strip())
    # Also check if any known hash in hash_to_resources maps to user_id
    for h, uid in email_hash_to_user.items():
        if uid == user_id:
            hashes_to_check.add(h)
    
    for h in hashes_to_check:
        for rid in evidence_idx.hash_to_resources.get(h, set()):
            if rid.startswith("account_"):
                resources["account"].add(rid)
            elif rid.startswith("search_"):
                resources["search"].add(rid)
            elif rid.startswith("analytics_"):
                resources["analytics"].add(rid)
            elif rid.startswith("backup_"):
                resources["backup"].add(rid)
            elif rid.startswith("security_") or rid.startswith("audit_record_"):
                resources["security"].add(rid)
            elif rid.startswith("data_flow_"):
                resources["data_flow"].add(rid)
            elif rid.startswith("tombstone_"):
                resources["tombstone"].add(rid)
    
    return resources


def get_user_number(user_id):
    """Extract the numeric part from user_id (e.g., 'user_05' -> 5)."""
    if not user_id:
        return None
    m = re.match(r'user_(\d+)', user_id)
    return int(m.group(1)) if m else None


def get_best_evidence_for_case(case, evidence_manifest, evidence_idx, user_id, resources):
    """Find the best evidence file_id to cite for a case based on audit_at time."""
    audit_at = case.get("audit_at", "")
    
    # Collect all file_ids that reference this user's resources
    file_ids = set()
    all_rids = set()
    for system_rids in resources.values():
        all_rids.update(system_rids)
    
    for rid in all_rids:
        for records_dict in [evidence_idx.account_records, evidence_idx.search_records,
                             evidence_idx.analytics_records, evidence_idx.support_records,
                             evidence_idx.export_records, evidence_idx.backup_records,
                             evidence_idx.security_records, evidence_idx.data_flow_records,
                             evidence_idx.tombstone_records, evidence_idx.marketing_records]:
            if rid in records_dict:
                fid, _ = records_dict[rid]
                file_ids.add(fid)
    
    if not file_ids:
        return ""
    
    # Find the evidence file closest to but not after audit_at
    best = None
    best_time = ""
    for fid in file_ids:
        meta = evidence_manifest.get(fid)
        if not meta:
            continue
        captured = meta.get("captured_at", "")
        if captured <= audit_at:
            if captured > best_time:
                best_time = captured
                best = fid
    
    return best if best else sorted(file_ids)[0]


def get_evidence_for_resource(rid, evidence_idx):
    """Get the evidence file_id for a specific resource."""
    for records_dict in [evidence_idx.account_records, evidence_idx.search_records,
                         evidence_idx.analytics_records, evidence_idx.support_records,
                         evidence_idx.export_records, evidence_idx.backup_records,
                         evidence_idx.security_records, evidence_idx.data_flow_records,
                         evidence_idx.tombstone_records, evidence_idx.marketing_records]:
        if rid in records_dict:
            fid, _ = records_dict[rid]
            return fid
    return ""


# ---------------------------------------------------------------------------
# 7. Step generation
# ---------------------------------------------------------------------------

# Operation ordering within each phase (from the spec table)
FINDING_OP_ORDER = {
    "REPORT_REMAINING_RECORD": 0,
    "REPORT_EXPOSED_PII": 1,
    "REPORT_ACTIVE_DATA_FLOW": 2,
    "REPORT_RESTORE_RISK": 3,
}

REMEDIATION_OP_ORDER = {
    "DISABLE_DATA_FLOW": 0,
    "BLOCK_RESTORE": 1,
    "DELETE_RECORD": 2,
    "REDACT_RECORD": 3,
    "ANONYMIZE_RECORD": 4,
}

VERIFICATION_OP_ORDER = {
    "VERIFY_RECORD_ABSENT": 0,
    "VERIFY_RECORD_PRESENT": 1,
    "VERIFY_RECORD_REDACTED": 2,
    "VERIFY_RECORD_ANONYMIZED": 3,
    "VERIFY_DATA_FLOW_DISABLED": 4,
    "VERIFY_RESTORE_BLOCKED": 5,
}


def step_sort_key(step):
    """Sort key for steps: phase order, then operation order, then system_id, then resource_id."""
    phase_order = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
    p = phase_order.get(step["phase"], 9)
    
    if step["phase"] == "FINDING":
        op = FINDING_OP_ORDER.get(step["operation"], 9)
    elif step["phase"] == "REMEDIATION":
        op = REMEDIATION_OP_ORDER.get(step["operation"], 9)
    else:
        op = VERIFICATION_OP_ORDER.get(step["operation"], 9)
    
    return (p, op, step.get("system_id", ""), step.get("resource_id", ""))


def analyze_case(case, user_id, emails, evidence_idx, evidence_manifest_dict, 
                 user_to_info, user_to_phones, email_hash_to_user, system_activity):
    """
    Analyze a single deletion case and return (deletion_status, steps).
    """
    # Check if deletion was actually requested
    request_text = case.get("request_text", "")
    if not is_deletion_requested(request_text):
        return "NOT_APPLICABLE", []
    
    if not user_id:
        # Can't resolve user - still process as deletion request
        # Look up by email directly
        pass
    
    # Find all resources for this user
    all_emails = set(emails) if emails else set()
    case_email = case["email"].strip().lower()
    all_emails.add(case_email)
    
    resources = find_user_resources(user_id, all_emails, evidence_idx, 
                                    user_to_info, user_to_phones, email_hash_to_user)
    
    steps = []
    is_complete = True
    
    # --- Analyze each system ---
    
    # 1. Account Service
    account_rids = sorted(resources["account"])
    account_absent_rids = []
    for rid in account_rids:
        if rid in evidence_idx.account_records:
            fid, rec = evidence_idx.account_records[rid]
            if is_record_absent(rec):
                account_absent_rids.append((rid, fid))
            else:
                # Account still present → FINDING + REMEDIATION needed
                is_complete = False
                steps.append({
                    "phase": "FINDING",
                    "system_id": "account_service",
                    "resource_id": rid,
                    "operation": "REPORT_REMAINING_RECORD",
                    "state": "PRESENT",
                    "evidence_id": fid,
                })
                steps.append({
                    "phase": "REMEDIATION",
                    "system_id": "account_service",
                    "resource_id": rid,
                    "operation": "DELETE_RECORD",
                    "state": "ABSENT",
                    "evidence_id": "",
                })
    
    # 2. Search Service
    search_rids = sorted(resources["search"])
    for rid in search_rids:
        if rid in evidence_idx.search_records:
            fid, rec = evidence_idx.search_records[rid]
            hits = rec.get("hits", {})
            docs = hits.get("documents", [])
            has_user_data = False
            for doc in docs:
                doc_email = (doc.get("email") or "").lower()
                if doc_email in all_emails:
                    has_user_data = True
                    break
                if doc.get("customer_reference") == user_id:
                    has_user_data = True
                    break
            
            if has_user_data or not docs:
                # Search record still present
                is_complete = False
                steps.append({
                    "phase": "FINDING",
                    "system_id": "search_service",
                    "resource_id": rid,
                    "operation": "REPORT_REMAINING_RECORD",
                    "state": "PRESENT",
                    "evidence_id": fid,
                })
                steps.append({
                    "phase": "REMEDIATION",
                    "system_id": "search_service",
                    "resource_id": rid,
                    "operation": "DELETE_RECORD",
                    "state": "ABSENT",
                    "evidence_id": "",
                })
    
    # 3. Analytics Platform
    analytics_rids = sorted(resources["analytics"])
    analytics_anon_rids = []
    for rid in analytics_rids:
        if rid in evidence_idx.analytics_records:
            fid, rec = evidence_idx.analytics_records[rid]
            if has_pii(rec):
                # Has exposed PII - needs anonymization
                is_complete = False
                steps.append({
                    "phase": "FINDING",
                    "system_id": "analytics_platform",
                    "resource_id": rid,
                    "operation": "REPORT_EXPOSED_PII",
                    "state": "PRESENT",
                    "evidence_id": fid,
                })
                steps.append({
                    "phase": "REMEDIATION",
                    "system_id": "analytics_platform",
                    "resource_id": rid,
                    "operation": "ANONYMIZE_RECORD",
                    "state": "ANONYMIZED",
                    "evidence_id": "",
                })
            else:
                # Already anonymized
                analytics_anon_rids.append((rid, fid))
    
    # 4. Support Platform  
    support_rids = sorted(resources["support"])
    support_redacted_rids = []
    for rid in support_rids:
        if rid in evidence_idx.support_records:
            fid, rec = evidence_idx.support_records[rid]
            if has_pii(rec):
                # Has exposed PII - needs redaction (support messages are REDACT per rules)
                is_complete = False
                steps.append({
                    "phase": "FINDING",
                    "system_id": "support_platform",
                    "resource_id": rid,
                    "operation": "REPORT_EXPOSED_PII",
                    "state": "PRESENT",
                    "evidence_id": fid,
                })
                # Determine if DELETE or REDACT based on rules
                # rule_05: SUPPORT_MESSAGE -> REDACT (if shared context)
                # rule_06: SUPPORT_ATTACHMENT -> DELETE (if belongs only to subject)
                # Default to REDACT for support tickets
                steps.append({
                    "phase": "REMEDIATION",
                    "system_id": "support_platform",
                    "resource_id": rid,
                    "operation": "REDACT_RECORD",
                    "state": "REDACTED",
                    "evidence_id": "",
                })
            else:
                support_redacted_rids.append((rid, fid))
    
    # Check if support record should be DELETE (attachment) vs REDACT (message)
    # From sample: support records use DELETE_RECORD for case_07 (attachment)
    # and REDACT_RECORD for case_19, case_29, case_30 (messages with shared context)
    # We need to check the request_text and evidence
    
    # 5. Export Service
    export_rids = sorted(resources["export"])
    for rid in export_rids:
        if rid in evidence_idx.export_records:
            fid, rec = evidence_idx.export_records[rid]
            # Exports should be deleted
            is_complete = False
            steps.append({
                "phase": "FINDING",
                "system_id": "export_service",
                "resource_id": rid,
                "operation": "REPORT_REMAINING_RECORD",
                "state": "PRESENT",
                "evidence_id": fid,
            })
            steps.append({
                "phase": "REMEDIATION",
                "system_id": "export_service",
                "resource_id": rid,
                "operation": "DELETE_RECORD",
                "state": "ABSENT",
                "evidence_id": "",
            })
    
    # 6. Integration Service (Data Flows)
    data_flow_rids = sorted(resources["data_flow"])
    data_flow_disabled_rids = []
    for rid in data_flow_rids:
        if rid in evidence_idx.data_flow_records:
            fid, rec = evidence_idx.data_flow_records[rid]
            if is_data_flow_active(rec):
                # Active data flow - needs to be disabled
                is_complete = False
                steps.append({
                    "phase": "FINDING",
                    "system_id": "integration_service",
                    "resource_id": rid,
                    "operation": "REPORT_ACTIVE_DATA_FLOW",
                    "state": "ACTIVE",
                    "evidence_id": fid,
                })
                steps.append({
                    "phase": "REMEDIATION",
                    "system_id": "integration_service",
                    "resource_id": rid,
                    "operation": "DISABLE_DATA_FLOW",
                    "state": "DISABLED",
                    "evidence_id": "",
                })
            else:
                data_flow_disabled_rids.append((rid, fid))
    
    # 7. Backup Service
    backup_rids = sorted(resources["backup"])
    backup_blocked_rids = []
    for rid in backup_rids:
        if rid in evidence_idx.backup_records:
            fid, rec = evidence_idx.backup_records[rid]
            if is_restore_allowed(rec):
                # Restore still allowed - needs blocking
                is_complete = False
                steps.append({
                    "phase": "FINDING",
                    "system_id": "backup_service",
                    "resource_id": rid,
                    "operation": "REPORT_RESTORE_RISK",
                    "state": "ACTIVE",
                    "evidence_id": fid,
                })
                steps.append({
                    "phase": "REMEDIATION",
                    "system_id": "backup_service",
                    "resource_id": rid,
                    "operation": "BLOCK_RESTORE",
                    "state": "BLOCKED",
                    "evidence_id": "",
                })
            else:
                backup_blocked_rids.append((rid, fid))
    
    # 8. Identity Service (Tombstones)
    tombstone_rids = sorted(resources["tombstone"])
    tombstone_redacted_rids = []
    for rid in tombstone_rids:
        if rid in evidence_idx.tombstone_records:
            fid, rec = evidence_idx.tombstone_records[rid]
            if has_pii(rec):
                # Tombstone still has PII - needs redaction
                is_complete = False
                steps.append({
                    "phase": "FINDING",
                    "system_id": "identity_service",
                    "resource_id": rid,
                    "operation": "REPORT_EXPOSED_PII",
                    "state": "PRESENT",
                    "evidence_id": fid,
                })
                steps.append({
                    "phase": "REMEDIATION",
                    "system_id": "identity_service",
                    "resource_id": rid,
                    "operation": "REDACT_RECORD",
                    "state": "REDACTED",
                    "evidence_id": "",
                })
            else:
                tombstone_redacted_rids.append((rid, fid))
    
    # --- Sort steps properly ---
    steps.sort(key=step_sort_key)
    
    # --- Add VERIFICATION steps ---
    verification_steps = []
    
    if is_complete:
        # COMPLETE: only verification steps proving current state
        # Account should be absent
        for rid, fid in account_absent_rids:
            verification_steps.append({
                "phase": "VERIFICATION",
                "system_id": "account_service",
                "resource_id": rid,
                "operation": "VERIFY_RECORD_ABSENT",
                "state": "ABSENT",
                "evidence_id": fid,
            })
        
        # If no explicit account found, generate one based on user number
        if not account_absent_rids and user_id:
            user_num = get_user_number(user_id)
            if user_num is not None:
                # Try to find evidence
                acct_rid = f"account_{user_num:03d}" if user_num < 100 else f"account_{user_num}"
                ev_fid = get_evidence_for_resource(acct_rid, evidence_idx)
                if not ev_fid:
                    # Find best evidence for this case
                    ev_fid = get_best_evidence_for_case(case, evidence_manifest_dict, evidence_idx, user_id, resources)
                verification_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": "account_service",
                    "resource_id": acct_rid,
                    "operation": "VERIFY_RECORD_ABSENT",
                    "state": "ABSENT",
                    "evidence_id": ev_fid,
                })
        
        # Security records should be present (retained)
        sec_rids = sorted(resources["security"])
        for rid in sec_rids:
            if rid in evidence_idx.security_records:
                fid, rec = evidence_idx.security_records[rid]
                verification_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": "security_service",
                    "resource_id": rid,
                    "operation": "VERIFY_RECORD_PRESENT",
                    "state": "PRESENT",
                    "evidence_id": fid,
                })
        
        # Analytics should be anonymized
        for rid, fid in analytics_anon_rids:
            verification_steps.append({
                "phase": "VERIFICATION",
                "system_id": "analytics_platform",
                "resource_id": rid,
                "operation": "VERIFY_RECORD_ANONYMIZED",
                "state": "ANONYMIZED",
                "evidence_id": fid,
            })
        
        # Support should be redacted
        for rid, fid in support_redacted_rids:
            verification_steps.append({
                "phase": "VERIFICATION",
                "system_id": "support_platform",
                "resource_id": rid,
                "operation": "VERIFY_RECORD_REDACTED",
                "state": "REDACTED",
                "evidence_id": fid,
            })
        
        # Data flows should be disabled
        for rid, fid in data_flow_disabled_rids:
            verification_steps.append({
                "phase": "VERIFICATION",
                "system_id": "integration_service",
                "resource_id": rid,
                "operation": "VERIFY_DATA_FLOW_DISABLED",
                "state": "DISABLED",
                "evidence_id": fid,
            })
        
        # Backups should be blocked
        for rid, fid in backup_blocked_rids:
            verification_steps.append({
                "phase": "VERIFICATION",
                "system_id": "backup_service",
                "resource_id": rid,
                "operation": "VERIFY_RESTORE_BLOCKED",
                "state": "BLOCKED",
                "evidence_id": fid,
            })
        
        # Tombstones should be redacted
        for rid, fid in tombstone_redacted_rids:
            verification_steps.append({
                "phase": "VERIFICATION",
                "system_id": "identity_service",
                "resource_id": rid,
                "operation": "VERIFY_RECORD_REDACTED",
                "state": "REDACTED",
                "evidence_id": fid,
            })
        
    else:
        # INCOMPLETE: add verification steps for what needs to be checked after remediation
        
        # Account verification
        for rid in account_rids:
            if rid in evidence_idx.account_records:
                verification_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": "account_service",
                    "resource_id": rid,
                    "operation": "VERIFY_RECORD_ABSENT",
                    "state": "ABSENT",
                    "evidence_id": "",
                })
        
        # If no explicit account, add one
        if not account_rids and user_id:
            user_num = get_user_number(user_id)
            if user_num is not None:
                acct_rid = f"account_{user_num:03d}" if user_num < 100 else f"account_{user_num}"
                verification_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": "account_service",
                    "resource_id": acct_rid,
                    "operation": "VERIFY_RECORD_ABSENT",
                    "state": "ABSENT",
                    "evidence_id": "",
                })
        
        # Search verification
        for rid in search_rids:
            verification_steps.append({
                "phase": "VERIFICATION",
                "system_id": "search_service",
                "resource_id": rid,
                "operation": "VERIFY_RECORD_ABSENT",
                "state": "ABSENT",
                "evidence_id": "",
            })
        
        # Security records
        sec_rids = sorted(resources["security"])
        for rid in sec_rids:
            verification_steps.append({
                "phase": "VERIFICATION",
                "system_id": "security_service",
                "resource_id": rid,
                "operation": "VERIFY_RECORD_PRESENT",
                "state": "PRESENT",
                "evidence_id": "",
            })
        
        # Support verification
        for rid in support_rids:
            if rid in evidence_idx.support_records:
                fid, rec = evidence_idx.support_records[rid]
                if has_pii(rec):
                    verification_steps.append({
                        "phase": "VERIFICATION",
                        "system_id": "support_platform",
                        "resource_id": rid,
                        "operation": "VERIFY_RECORD_REDACTED",
                        "state": "REDACTED",
                        "evidence_id": "",
                    })
        
        # Analytics verification
        for rid in analytics_rids:
            if rid in evidence_idx.analytics_records:
                fid, rec = evidence_idx.analytics_records[rid]
                if has_pii(rec):
                    verification_steps.append({
                        "phase": "VERIFICATION",
                        "system_id": "analytics_platform",
                        "resource_id": rid,
                        "operation": "VERIFY_RECORD_ANONYMIZED",
                        "state": "ANONYMIZED",
                        "evidence_id": "",
                    })
        
        # Export verification
        for rid in export_rids:
            verification_steps.append({
                "phase": "VERIFICATION",
                "system_id": "export_service",
                "resource_id": rid,
                "operation": "VERIFY_RECORD_ABSENT",
                "state": "ABSENT",
                "evidence_id": "",
            })
        
        # Data flow verification
        for rid in data_flow_rids:
            if rid in evidence_idx.data_flow_records:
                fid, rec = evidence_idx.data_flow_records[rid]
                if is_data_flow_active(rec):
                    verification_steps.append({
                        "phase": "VERIFICATION",
                        "system_id": "integration_service",
                        "resource_id": rid,
                        "operation": "VERIFY_DATA_FLOW_DISABLED",
                        "state": "DISABLED",
                        "evidence_id": "",
                    })
        
        # Backup verification
        for rid in backup_rids:
            if rid in evidence_idx.backup_records:
                fid, rec = evidence_idx.backup_records[rid]
                if is_restore_allowed(rec):
                    verification_steps.append({
                        "phase": "VERIFICATION",
                        "system_id": "backup_service",
                        "resource_id": rid,
                        "operation": "VERIFY_RESTORE_BLOCKED",
                        "state": "BLOCKED",
                        "evidence_id": "",
                    })
        
        # Tombstone verification
        for rid in tombstone_rids:
            if rid in evidence_idx.tombstone_records:
                fid, rec = evidence_idx.tombstone_records[rid]
                if has_pii(rec):
                    verification_steps.append({
                        "phase": "VERIFICATION",
                        "system_id": "identity_service",
                        "resource_id": rid,
                        "operation": "VERIFY_RECORD_REDACTED",
                        "state": "REDACTED",
                        "evidence_id": "",
                    })
    
    # Sort verification steps
    verification_steps.sort(key=step_sort_key)
    
    # Combine all steps
    all_steps = steps + verification_steps
    
    # Re-number steps
    for i, step in enumerate(all_steps, 1):
        step["step_no"] = i
    
    status = "COMPLETE" if is_complete else "INCOMPLETE"
    
    return status, all_steps


# ---------------------------------------------------------------------------
# 8. Also analyze system_activity for additional context
# ---------------------------------------------------------------------------

def build_activity_index(activities):
    """Build indexes from system_activity.csv."""
    # resource_id -> list of activities
    rid_to_activities = defaultdict(list)
    for act in activities:
        rid = act.get("resource_id", "")
        if rid:
            rid_to_activities[rid].append(act)
    return rid_to_activities


# ---------------------------------------------------------------------------
# 9. Main processing
# ---------------------------------------------------------------------------

def process_all_cases():
    """Process all deletion requests and generate output.csv."""
    print("Loading data...")
    
    # Load all CSVs
    deletion_requests = load_deletion_requests()
    sample_requests = load_sample_requests()
    sample_output = load_sample_output()
    identities = load_user_identities()
    audit_log = load_user_audit_log()
    activities = load_system_activity()
    rules = load_deletion_rules()
    evidence_manifest = load_evidence_files()
    
    print(f"  Deletion requests: {len(deletion_requests)}")
    print(f"  Sample requests: {len(sample_requests)}")
    print(f"  User identities: {len(identities)}")
    print(f"  Audit log entries: {len(audit_log)}")
    print(f"  System activities: {len(activities)}")
    print(f"  Evidence files: {len(evidence_manifest)}")
    
    # Build identity maps
    print("Building identity maps...")
    email_to_user, user_to_emails, user_to_info, user_to_phones, email_hash_to_user, name_to_user, user_to_hashes = \
        build_identity_maps(identities, audit_log)
    
    # Build activity index
    activity_index = build_activity_index(activities)
    
    # Build evidence index
    print("Indexing evidence files...")
    evidence_idx = EvidenceIndex(evidence_manifest)
    evidence_manifest_dict = {e["file_id"]: e for e in evidence_manifest}
    
    print(f"  Indexed accounts: {len(evidence_idx.account_records)}")
    print(f"  Indexed search: {len(evidence_idx.search_records)}")
    print(f"  Indexed analytics: {len(evidence_idx.analytics_records)}")
    print(f"  Indexed support: {len(evidence_idx.support_records)}")
    print(f"  Indexed exports: {len(evidence_idx.export_records)}")
    print(f"  Indexed backups: {len(evidence_idx.backup_records)}")
    print(f"  Indexed security: {len(evidence_idx.security_records)}")
    print(f"  Indexed data flows: {len(evidence_idx.data_flow_records)}")
    print(f"  Indexed tombstones: {len(evidence_idx.tombstone_records)}")
    
    # Process only requests in deletion_requests.csv (exactly 518 cases)
    all_cases = {}  # case_id -> (status, steps_json_str)
    
    print(f"Processing {len(deletion_requests)} cases...")
    for i, case in enumerate(deletion_requests):
        case_id = case["case_id"]
        
        if i % 50 == 0:
            print(f"  Processing case {i+1}/{len(deletion_requests)}...")
        
        # Resolve user identity
        case_email = case["email"].strip().lower()
        user_id = resolve_user(case_email, email_to_user)
        
        if user_id:
            emails = user_to_emails.get(user_id, set())
        else:
            emails = {case_email}
        
        # Analyze the case
        status, steps = analyze_case(
            case, user_id, emails, evidence_idx, evidence_manifest_dict,
            user_to_info, user_to_phones, email_hash_to_user, activities
        )
        
        # Format steps as JSON
        # Remove internal keys
        clean_steps = []
        for s in steps:
            clean_steps.append({
                "step_no": s["step_no"],
                "phase": s["phase"],
                "system_id": s["system_id"],
                "resource_id": s["resource_id"],
                "operation": s["operation"],
                "state": s["state"],
                "evidence_id": s["evidence_id"],
            })
        
        steps_json = json.dumps(clean_steps, separators=(",", ":"))
        all_cases[case_id] = (status, steps_json)
    
    # Write output.csv
    print(f"Writing {len(all_cases)} cases to output.csv...")
    
    # Sort by case_id (numeric sort)
    def case_sort_key(cid):
        m = re.match(r'case_(\d+)', cid)
        return int(m.group(1)) if m else 0
    
    sorted_case_ids = sorted(all_cases.keys(), key=case_sort_key)
    
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "deletion_status", "steps_json"])
        for case_id in sorted_case_ids:
            status, steps_json = all_cases[case_id]
            writer.writerow([case_id, status, steps_json])
    
    print(f"Done! Output written to {OUTPUT_PATH}")
    print(f"Total cases: {len(sorted_case_ids)}")
    
    # Verify count
    expected = len(deletion_requests)
    if len(sorted_case_ids) != expected:
        print(f"WARNING: Expected {expected} cases, got {len(sorted_case_ids)}")


if __name__ == "__main__":
    process_all_cases()
