#!/usr/bin/env python3
"""Step 0: Data profiling audit for data/data.snapshot.csv. Prints summary + writes data/profile_report.txt."""
import os
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "data" / "data.snapshot.csv"
REPORT = ROOT / "data" / "profile_report.txt"

lines: list[str] = []

def emit(s: str = ""):
    print(s)
    lines.append(s)

# --- Load ---
size_mb = SNAP.stat().st_size / 1024 / 1024
df = pd.read_csv(SNAP, encoding="utf-8", low_memory=False)
emit(f"File: {SNAP}")
emit(f"Size: {size_mb:.1f} MB")
emit(f"Rows: {len(df):,}  Columns: {len(df.columns)}")
emit(f"Columns: {list(df.columns)}")
emit("")

# --- Coverage skew (most important) ---
emit("=" * 70)
emit("PER-SUBDOMAIN COVERAGE (the single most important context)")
emit("=" * 70)
sub_counts = df["subdomain"].value_counts()
emit(f"Distinct subdomains: {sub_counts.size}")
top = sub_counts.head(20)
total = len(df)
for sd, n in top.items():
    emit(f"  {sd:<25s} {n:>8,}  ({100*n/total:5.2f}%)")
emit(f"  ... {sub_counts.size - 20} more subdomains" if sub_counts.size > 20 else "")
dominant = sub_counts.iloc[0]
emit(f"\nLargest subdomain ({sub_counts.index[0]}) = {100*dominant/total:.2f}% of rows")
if dominant / total > 0.25:
    emit("⚠️  COVERAGE WARNING: single subdomain >25% of rows. Lead README with this disclosure.")
emit("")

# --- Per-university ---
emit("=" * 70)
emit("PER-UNIVERSITY ROW COUNTS (top 20)")
emit("=" * 70)
uni_counts = df.groupby(["university_id", "university_name"]).size().sort_values(ascending=False)
for (uid, uname), n in uni_counts.head(20).items():
    name = (uname[:60] + "…") if len(str(uname)) > 60 else uname
    emit(f"  {uid:<10} {name:<62s} {n:>8,}")
emit("")

# --- 1-to-1 invariants: subdomain ↔ university_id ↔ university_name ---
emit("=" * 70)
emit("CROSS-COLUMN CONSISTENCY")
emit("=" * 70)
sub_to_uid = df.groupby("subdomain")["university_id"].nunique()
bad = sub_to_uid[sub_to_uid > 1]
emit(f"Subdomains mapping to >1 university_id: {len(bad)}")
if len(bad):
    emit(f"  examples: {bad.head().to_dict()}")
uid_to_name = df.groupby("university_id")["university_name"].nunique()
bad = uid_to_name[uid_to_name > 1]
emit(f"university_ids with >1 university_name: {len(bad)}")
if len(bad):
    emit(f"  examples: {bad.head().to_dict()}")
# department_id consistency within university
dept_name_drift = df.groupby(["university_id", "department_id"])["department_name"].nunique()
bad = dept_name_drift[dept_name_drift > 1]
emit(f"(university_id, department_id) pairs with >1 department_name: {len(bad)}")
# subdomain extracted from profile_url matches subdomain column
def _sub_from_url(u: str) -> str:
    try:
        return u.split("//", 1)[1].split(".academia.edu", 1)[0]
    except Exception:
        return ""
url_sub = df["profile_url"].astype(str).apply(_sub_from_url)
mismatch = (url_sub != df["subdomain"]).sum()
emit(f"Rows where subdomain != extracted-from-profile_url: {mismatch}")
# has_photo iff /images/s65_no_pic.png
no_pic = df["photo_url"] == "/images/s65_no_pic.png"
hp_false = df["has_photo"].astype(str) == "False"
agreement = (no_pic == hp_false).sum()
emit(f"`has_photo == False` iff placeholder photo URL: {agreement:,} / {len(df):,} agree")
emit("")

# --- Duplicates ---
emit("=" * 70)
emit("DUPLICATE CHECKS")
emit("=" * 70)
dup_uid = df["user_id"].duplicated().sum()
emit(f"Duplicate user_id rows:                  {dup_uid}")
dup_sub_page = df.duplicated(["subdomain", "page_name"]).sum()
emit(f"Duplicate (subdomain, page_name) rows:   {dup_sub_page}")
dup_url = df["profile_url"].duplicated().sum()
emit(f"Duplicate profile_url rows:              {dup_url}")
emit("")

# --- Missing/empty per column ---
emit("=" * 70)
emit("MISSING / EMPTY RATES (% of total rows)")
emit("=" * 70)
for col in df.columns:
    s = df[col]
    # treat NaN + empty-string as missing
    miss = s.isna().sum() + (s.astype(str).str.strip() == "").sum() - s.isna().sum()
    total_miss = s.isna().sum() + ((s.astype(str).str.strip() == "") & s.notna()).sum()
    if total_miss:
        emit(f"  {col:<24s} {total_miss:>8,}  ({100*total_miss/len(df):5.2f}%)")
emit("")

# --- Numeric distributions after imputing zero ---
emit("=" * 70)
emit("NUMERIC DISTRIBUTIONS (empty → 0 for engagement fields)")
emit("=" * 70)
for col in ["followers_count", "following_count", "papers_count"]:
    v = pd.to_numeric(df[col], errors="coerce").fillna(0)
    desc = v.describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.99])
    emit(f"\n  {col}")
    for k in ["min", "25%", "50%", "75%", "90%", "99%", "max", "mean"]:
        emit(f"    {k:<6s} {desc[k]:>12,.1f}")
emit("")

# --- author_rank ---
emit("=" * 70)
emit("AUTHOR RANK & BRAGWORTHY")
emit("=" * 70)
ar = pd.to_numeric(df["author_rank"], errors="coerce")
floor = (ar == 1).sum()
ranked = (ar > 1).sum()
emit(f"author_rank == 1 (floor):     {floor:>9,}  ({100*floor/len(df):5.2f}%)")
emit(f"author_rank > 1  (ranked):    {ranked:>9,}  ({100*ranked/len(df):5.2f}%)")
if ranked:
    rr = ar[ar > 1]
    emit(f"  ranked subset: min={rr.min():.2f} median={rr.median():.2f} max={rr.max():.2f}")
brag = (df["bragworthy"].astype(str) == "True").sum()
emit(f"bragworthy == True:           {brag:>9,}  ({100*brag/len(df):5.4f}%)")
emit("")

# --- has_photo ---
emit("=" * 70)
emit("PHOTO COMPLETENESS")
emit("=" * 70)
hp_true = (df["has_photo"].astype(str) == "True").sum()
emit(f"has_photo == True:            {hp_true:>9,}  ({100*hp_true/len(df):5.2f}%)")
emit("")

# --- created_at year distribution ---
emit("=" * 70)
emit("ACCOUNT CREATION BY YEAR")
emit("=" * 70)
years = pd.to_datetime(df["created_at"], errors="coerce", utc=True).dt.year
yc = years.value_counts().sort_index()
for y, n in yc.items():
    emit(f"  {int(y):<6d} {n:>9,}")
emit("")

# --- Department-level top ---
emit("=" * 70)
emit("PER-DEPARTMENT ROW COUNTS (top 20)")
emit("=" * 70)
dc = df.groupby(["university_name", "department_name"]).size().sort_values(ascending=False)
for (uname, dname), n in dc.head(20).items():
    short = f"{str(uname)[:30]} / {str(dname)[:35]}"
    emit(f"  {short:<70s} {n:>6,}")
emit("")

# --- Save ---
REPORT.write_text("\n".join(lines), encoding="utf-8")
emit(f"\nSaved report to {REPORT}")
