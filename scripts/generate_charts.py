#!/usr/bin/env python3
"""Step 1: generate all required business-analysis charts from data/data.snapshot.csv into charts/.

Conventions:
- Single colour palette (sns 'crest' for sequential, sns 'rocket' for diverging accents).
- No pie charts.
- All PNG @ 150+ DPI, constrained_layout=True.
- University-aggregated charts: only universities with >=MIN_UNIV_ROWS rows.
- Engagement numeric fields imputed empty -> 0.
- Coverage check: if any subdomain > 50% of rows, emit a coverage-warning chart.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LogNorm

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "data" / "data.snapshot.csv"
OUT = ROOT / "charts"
OUT.mkdir(parents=True, exist_ok=True)

# --- Tunables ---
MIN_UNIV_ROWS = 50         # exclude tiny partial scrapes from university-level charts
TOP_N_UNI = 20
TOP_N_BIG = 30
DPI = 160

sns.set_theme(
    style="whitegrid",
    rc={
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "figure.titlesize": 14,
        "font.family": "DejaVu Sans",  # broad Unicode coverage
    },
)
PRIMARY = "#1f4e79"
ACCENT = "#c0392b"
PALETTE = sns.color_palette("crest", as_cmap=False, n_colors=20)


def save(fig, name: str):
    p = OUT / f"{name}.png"
    fig.savefig(p, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {p.name}")


def shorten(s: str, n: int = 40) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


COUNTRY_MAP = {
    "au": "Australia", "uk": "United Kingdom", "az": "Azerbaijan",
    "hk": "Hong Kong", "nz": "New Zealand", "ar": "Argentina",
    "fr": "France", "de": "Germany", "ru": "Russia", "ca": "Canada",
    "jp": "Japan", "kr": "South Korea", "in": "India", "nl": "Netherlands",
    "no": "Norway", "se": "Sweden", "ch": "Switzerland", "be": "Belgium",
    "ie": "Ireland", "tw": "Taiwan", "sg": "Singapore", "my": "Malaysia",
    "ph": "Philippines", "th": "Thailand", "tr": "Turkey", "es": "Spain",
    "it": "Italy", "pt": "Portugal", "pl": "Poland", "br": "Brazil",
    "mx": "Mexico", "cl": "Chile", "co": "Colombia", "za": "South Africa",
    "il": "Israel", "ae": "UAE", "sa": "Saudi Arabia", "ng": "Nigeria",
    "ke": "Kenya", "gr": "Greece", "fi": "Finland", "dk": "Denmark",
    "at": "Austria", "cz": "Czechia", "hu": "Hungary", "ro": "Romania",
}
# Manual overrides for subdomains without a country suffix that aren't US.
OVERRIDES = {
    "ucl": "United Kingdom", "oxford": "United Kingdom", "cambridge": "United Kingdom",
    "leeds": "United Kingdom", "leicester": "United Kingdom", "nottingham": "United Kingdom",
    "kcl": "United Kingdom", "soton": "United Kingdom", "brighton": "United Kingdom",
    "qub": "United Kingdom", "manchester": "United Kingdom",
    "kashanu": "Iran", "crete": "Greece", "kuleuven": "Belgium",
    "sorbonne-fr": "France", "kristiania": "Norway", "tilburguniversity": "Netherlands",
    "sissa": "Italy", "kaist": "South Korea", "hiroshima-u": "Japan",
    "maynoothcollege": "Ireland",
}

def country_for(sd: str) -> str:
    if sd in OVERRIDES:
        return OVERRIDES[sd]
    m = re.search(r"-([a-z]{2})$", sd)
    if m and m.group(1) in COUNTRY_MAP:
        return COUNTRY_MAP[m.group(1)]
    return "USA / Other"


def main():
    print(f"Loading {SNAP}…")
    df = pd.read_csv(SNAP, encoding="utf-8", low_memory=False)
    print(f"  {len(df):,} rows, {df['subdomain'].nunique()} subdomains")

    # --- Impute engagement zeros ---
    for col in ("followers_count", "following_count", "papers_count"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df["author_rank"] = pd.to_numeric(df["author_rank"], errors="coerce")
    df["bragworthy"] = df["bragworthy"].astype(str) == "True"
    df["has_photo"] = df["has_photo"].astype(str) == "True"
    df["has_about"] = df["about"].fillna("").astype(str).str.strip() != ""
    df["has_email"] = df["public_email"].fillna("").astype(str).str.strip() != ""
    df["completeness"] = df[["has_about", "has_email", "has_photo"]].sum(axis=1)
    df["created_dt"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    df["created_year"] = df["created_dt"].dt.year
    df["country"] = df["subdomain"].apply(country_for)

    # Per-uni filter: subdomains with >= MIN_UNIV_ROWS rows
    sub_counts = df["subdomain"].value_counts()
    big_subs = sub_counts[sub_counts >= MIN_UNIV_ROWS].index
    big = df[df["subdomain"].isin(big_subs)].copy()
    print(f"  {len(big_subs)} subdomains with >= {MIN_UNIV_ROWS} rows (used for per-uni charts)")

    # === Volume & Coverage ===
    print("\n[Volume & Coverage]")

    fig, ax = plt.subplots(figsize=(8, 4))
    overview = {
        "Researchers": len(df),
        "Universities": df["subdomain"].nunique(),
        "Departments": df.groupby(["university_id", "department_id"]).ngroups,
    }
    bars = ax.bar(overview.keys(), overview.values(), color=[PRIMARY, "#2980b9", "#5dade2"])
    for b, v in zip(bars, overview.values()):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:,}",
                ha="center", va="bottom", fontsize=12, fontweight="bold")
    ax.set_title("Registry overview")
    ax.set_ylabel("Count")
    ax.set_yscale("log")
    save(fig, "01_overview_counts")

    # Researchers per university - top 20 (h-bar)
    uni_n = (df.groupby(["subdomain", "university_name"]).size()
             .reset_index(name="n").sort_values("n", ascending=False))
    top = uni_n.head(TOP_N_UNI)
    fig, ax = plt.subplots(figsize=(11, 8))
    labels = [f"{shorten(r.university_name, 38)}  [{r.subdomain}]" for r in top.itertuples()]
    ax.barh(labels, top["n"], color=PRIMARY)
    ax.invert_yaxis()
    ax.set_xlabel("Researchers")
    ax.set_title(f"Top {TOP_N_UNI} universities by researcher count")
    for i, v in enumerate(top["n"]):
        ax.text(v, i, f" {v:,}", va="center", fontsize=9)
    save(fig, "02_top_universities_by_count")

    # Researchers per university — full distribution (histogram, log-x)
    fig, ax = plt.subplots(figsize=(9, 5))
    bins = np.logspace(np.log10(max(1, uni_n["n"].min())), np.log10(uni_n["n"].max()), 30)
    ax.hist(uni_n["n"], bins=bins, color=PRIMARY, edgecolor="white")
    ax.set_xscale("log")
    ax.set_xlabel("Researchers per university (log scale)")
    ax.set_ylabel("# universities")
    ax.set_title("Distribution of researcher counts per university")
    ax.axvline(uni_n["n"].median(), color=ACCENT, linestyle="--",
               label=f"Median = {uni_n['n'].median():,.0f}")
    ax.legend()
    save(fig, "03_university_count_distribution")

    # Top 30 departments
    dep_n = (df.groupby(["subdomain", "university_name", "department_name"]).size()
             .reset_index(name="n").sort_values("n", ascending=False))
    top_d = dep_n.head(TOP_N_BIG)
    fig, ax = plt.subplots(figsize=(11, 11))
    labels = [f"{shorten(r.department_name, 32)} @ {shorten(r.university_name, 22)}"
              for r in top_d.itertuples()]
    ax.barh(labels, top_d["n"], color=PALETTE[3])
    ax.invert_yaxis()
    ax.set_xlabel("Researchers")
    ax.set_title(f"Top {TOP_N_BIG} departments by researcher count")
    for i, v in enumerate(top_d["n"]):
        ax.text(v, i, f" {v:,}", va="center", fontsize=8)
    save(fig, "04_top_departments_by_count")

    # Department-size distribution
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(dep_n["n"], bins=range(0, int(dep_n["n"].max()) + 10, 10),
            color=PALETTE[5], edgecolor="white")
    ax.set_xlabel("Researchers per department (bin width = 10)")
    ax.set_ylabel("# departments")
    ax.set_title("Distribution of researcher counts per department")
    ax.set_yscale("log")
    ax.axvline(dep_n["n"].median(), color=ACCENT, linestyle="--",
               label=f"Median = {dep_n['n'].median():.0f}")
    ax.legend()
    save(fig, "05_department_count_distribution")

    # Coverage warning chart only if dominance > 50%
    largest = sub_counts.iloc[0] / len(df)
    if largest > 0.5:
        fig, ax = plt.subplots(figsize=(8, 3))
        labels = [sub_counts.index[0], "All others"]
        vals = [sub_counts.iloc[0], len(df) - sub_counts.iloc[0]]
        ax.barh(labels, vals, color=[ACCENT, PRIMARY])
        ax.set_xlabel("Rows in CSV")
        ax.set_title(f"Coverage warning: one subdomain = {largest*100:.1f}% of dataset")
        for i, v in enumerate(vals):
            ax.text(v, i, f" {v:,}", va="center")
        save(fig, "06_coverage_warning")
    else:
        # no warning needed but still show coverage spread
        fig, ax = plt.subplots(figsize=(9, 5))
        top_share = sub_counts.head(15) / len(df) * 100
        ax.barh(top_share.index, top_share.values, color=PRIMARY)
        ax.invert_yaxis()
        ax.set_xlabel("% of total rows")
        ax.set_title(f"Coverage spread — largest subdomain only {largest*100:.1f}% of dataset (no skew)")
        for i, v in enumerate(top_share.values):
            ax.text(v, i, f" {v:.1f}%", va="center", fontsize=9)
        save(fig, "06_coverage_spread")

    # === Account age ===
    print("\n[Account age]")

    yc = df["created_year"].dropna().astype(int).value_counts().sort_index()
    yc = yc[yc.index >= 2007]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(yc.index.astype(str), yc.values, color=PRIMARY)
    ax.set_title("Researchers by account-creation year")
    ax.set_xlabel("Year"); ax.set_ylabel("Accounts created")
    for i, v in enumerate(yc.values):
        if v > yc.values.max() * 0.04:
            ax.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=8)
    ax.tick_params(axis="x", rotation=45)
    save(fig, "07_accounts_per_year")

    # Monthly last 24 months
    last_dt = df["created_dt"].max()
    if pd.notna(last_dt):
        cutoff = last_dt - pd.DateOffset(months=24)
        recent = df[df["created_dt"] >= cutoff].copy()
        recent["ym"] = recent["created_dt"].dt.to_period("M").dt.to_timestamp()
        m = recent.groupby("ym").size()
        if len(m) > 1:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(m.index, m.values, marker="o", color=PRIMARY)
            ax.set_title("Monthly account creations — last 24 months")
            ax.set_ylabel("Accounts created"); ax.set_xlabel("Month")
            ax.tick_params(axis="x", rotation=45)
            save(fig, "08_monthly_recent")

    # Median account age (years) by university, top 20
    today = pd.Timestamp.now(tz="UTC")
    df["age_years"] = (today - df["created_dt"]).dt.days / 365.25
    uni_age = (df[df["subdomain"].isin(big_subs)]
               .groupby(["subdomain", "university_name"])["age_years"].median()
               .sort_values(ascending=False).head(TOP_N_UNI))
    fig, ax = plt.subplots(figsize=(11, 8))
    labels = [f"{shorten(name, 38)}  [{sd}]" for (sd, name) in uni_age.index]
    ax.barh(labels, uni_age.values, color=PALETTE[7])
    ax.invert_yaxis()
    ax.set_xlabel("Median account age (years)")
    ax.set_title(f"Top {TOP_N_UNI} universities by median account age (earliest adopters)")
    for i, v in enumerate(uni_age.values):
        ax.text(v, i, f" {v:.1f}", va="center", fontsize=9)
    save(fig, "09_median_account_age_by_university")

    # === Engagement ===
    print("\n[Engagement]")

    # Followers histogram log-y
    fig, ax = plt.subplots(figsize=(10, 5))
    f = df["followers_count"]
    bins = [0, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 10000, 100000, 300000]
    ax.hist(f, bins=bins, color=PRIMARY, edgecolor="white")
    ax.set_xscale("symlog"); ax.set_yscale("log")
    ax.set_xlabel("Followers (symlog scale)"); ax.set_ylabel("# researchers (log)")
    ax.set_title("Distribution of follower counts")
    for q, lab in [(0.5, "median"), (0.9, "p90"), (0.99, "p99")]:
        ax.axvline(f.quantile(q), color=ACCENT, linestyle="--", alpha=0.7,
                   label=f"{lab} = {int(f.quantile(q))}")
    ax.legend()
    save(fig, "10_followers_distribution")

    # Following histogram
    fig, ax = plt.subplots(figsize=(10, 5))
    g = df["following_count"]
    bins = [0, 1, 2, 5, 10, 25, 50, 100, 250, 1000, 5000]
    ax.hist(g, bins=bins, color=PALETTE[6], edgecolor="white")
    ax.set_xscale("symlog"); ax.set_yscale("log")
    ax.set_xlabel("Following (symlog scale)"); ax.set_ylabel("# researchers (log)")
    ax.set_title("Distribution of following counts")
    for q, lab in [(0.5, "median"), (0.9, "p90"), (0.99, "p99")]:
        ax.axvline(g.quantile(q), color=ACCENT, linestyle="--", alpha=0.7,
                   label=f"{lab} = {int(g.quantile(q))}")
    ax.legend()
    save(fig, "11_following_distribution")

    # Papers histogram with 0-bar distinct
    fig, ax = plt.subplots(figsize=(10, 5))
    p = df["papers_count"]
    zero = (p == 0).sum()
    nonzero = p[p > 0]
    bins = [1, 2, 3, 5, 8, 13, 21, 34, 55, 100, 250, 1000, 2000]
    ax.bar(["0 papers"], [zero], color=ACCENT, label=f"0 papers ({100*zero/len(p):.1f}%)")
    n_nz, b_edges = np.histogram(nonzero, bins=bins)
    xs = [f"{int(b_edges[i])}–{int(b_edges[i+1])}" for i in range(len(n_nz))]
    ax.bar(xs, n_nz, color=PRIMARY)
    ax.set_yscale("log")
    ax.set_title("Researchers by papers-published count")
    ax.set_ylabel("# researchers (log)")
    ax.tick_params(axis="x", rotation=45)
    ax.legend()
    save(fig, "12_papers_distribution")

    # Share with >=1 paper, by university top 20
    paper_share = (big.groupby(["subdomain", "university_name"])
                   .apply(lambda g: (g["papers_count"] >= 1).mean() * 100, include_groups=False)
                   .sort_values(ascending=False).head(TOP_N_UNI))
    fig, ax = plt.subplots(figsize=(11, 8))
    labels = [f"{shorten(name, 38)}  [{sd}]" for (sd, name) in paper_share.index]
    ax.barh(labels, paper_share.values, color=PALETTE[4])
    ax.invert_yaxis(); ax.set_xlabel("% of researchers with ≥1 paper")
    ax.set_title(f"Top {TOP_N_UNI} universities by paper-publication rate")
    for i, v in enumerate(paper_share.values):
        ax.text(v, i, f" {v:.1f}%", va="center", fontsize=9)
    save(fig, "13_paper_share_by_university")

    # Share with >=10 followers, top 20
    fol_share = (big.groupby(["subdomain", "university_name"])
                 .apply(lambda g: (g["followers_count"] >= 10).mean() * 100, include_groups=False)
                 .sort_values(ascending=False).head(TOP_N_UNI))
    fig, ax = plt.subplots(figsize=(11, 8))
    labels = [f"{shorten(name, 38)}  [{sd}]" for (sd, name) in fol_share.index]
    ax.barh(labels, fol_share.values, color=PALETTE[9])
    ax.invert_yaxis(); ax.set_xlabel("% of researchers with ≥10 followers")
    ax.set_title(f"Top {TOP_N_UNI} universities by ≥10-follower rate")
    for i, v in enumerate(fol_share.values):
        ax.text(v, i, f" {v:.1f}%", va="center", fontsize=9)
    save(fig, "14_follower10_share_by_university")

    # Followers vs Papers scatter (log-log), label top 30 by followers
    sample = df[(df["followers_count"] > 0) | (df["papers_count"] > 0)]
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.scatter(sample["papers_count"] + 1, sample["followers_count"] + 1,
               s=4, alpha=0.15, color=PRIMARY)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("Papers + 1 (log)"); ax.set_ylabel("Followers + 1 (log)")
    ax.set_title("Followers vs Papers (researchers with any signal). Top-30 labelled.")
    top_f = df.nlargest(30, "followers_count")
    for _, r in top_f.iterrows():
        ax.annotate(shorten(str(r["display_name"]), 22),
                    xy=(r["papers_count"] + 1, r["followers_count"] + 1),
                    fontsize=7, alpha=0.85, color=ACCENT)
    save(fig, "15_followers_vs_papers_scatter")

    # Top 25 most-followed
    top_fol = df.nlargest(25, "followers_count")
    fig, ax = plt.subplots(figsize=(11, 9))
    labels = [f"{shorten(r.display_name, 28)} @ {shorten(r.university_name, 25)}"
              for r in top_fol.itertuples()]
    ax.barh(labels, top_fol["followers_count"], color=PRIMARY)
    ax.invert_yaxis(); ax.set_xlabel("Followers")
    ax.set_title("Top 25 most-followed researchers")
    for i, v in enumerate(top_fol["followers_count"]):
        ax.text(v, i, f" {int(v):,}", va="center", fontsize=8)
    save(fig, "16_top_followed_researchers")

    # Top 25 most-published
    top_pap = df.nlargest(25, "papers_count")
    fig, ax = plt.subplots(figsize=(11, 9))
    labels = [f"{shorten(r.display_name, 28)} @ {shorten(r.university_name, 25)}"
              for r in top_pap.itertuples()]
    ax.barh(labels, top_pap["papers_count"], color=PALETTE[2])
    ax.invert_yaxis(); ax.set_xlabel("Papers uploaded")
    ax.set_title("Top 25 most-published researchers")
    for i, v in enumerate(top_pap["papers_count"]):
        ax.text(v, i, f" {int(v):,}", va="center", fontsize=8)
    save(fig, "17_top_published_researchers")

    # Following/Followers ratio
    df_pop = df[df["followers_count"] >= 5].copy()
    df_pop["ratio"] = df_pop["following_count"] / df_pop["followers_count"]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(df_pop["ratio"].clip(upper=10), bins=40, color=PALETTE[8], edgecolor="white")
    ax.set_xlabel("Following / Followers ratio (researchers with ≥5 followers, clipped at 10)")
    ax.set_ylabel("# researchers")
    ax.set_title("Following / Followers ratio distribution")
    ax.axvline(0.5, color=ACCENT, linestyle="--", label="0.5 (popular)")
    ax.axvline(2.0, color="#27ae60", linestyle="--", label="2.0 (curator/seeker)")
    ax.legend()
    save(fig, "18_following_follower_ratio")

    # === Profile completeness ===
    print("\n[Profile completeness]")

    for col, label, name in [
        ("has_about", "% with bio populated", "19_about_share_by_university"),
        ("has_email", "% with public email", "20_email_share_by_university"),
        ("has_photo", "% with profile photo", "21_photo_share_by_university"),
    ]:
        share = (big.groupby(["subdomain", "university_name"])[col].mean() * 100
                 ).sort_values(ascending=False).head(TOP_N_UNI)
        fig, ax = plt.subplots(figsize=(11, 8))
        lbls = [f"{shorten(n, 38)}  [{sd}]" for (sd, n) in share.index]
        ax.barh(lbls, share.values, color=PRIMARY)
        ax.invert_yaxis(); ax.set_xlabel(label)
        ax.set_title(f"Top {TOP_N_UNI} universities by {label.lower()}")
        for i, v in enumerate(share.values):
            ax.text(v, i, f" {v:.1f}%", va="center", fontsize=9)
        save(fig, name)

    # Composite completeness (0-3) histogram
    fig, ax = plt.subplots(figsize=(8, 4.5))
    cc = df["completeness"].value_counts().sort_index()
    bars = ax.bar(cc.index.astype(str), cc.values,
                  color=[ACCENT, "#e67e22", PALETTE[10], "#27ae60"])
    ax.set_xlabel("Profile-completeness score (about + email + photo, 0–3)")
    ax.set_ylabel("# researchers")
    ax.set_title("Profile completeness across the entire registry")
    for b, v in zip(bars, cc.values):
        ax.text(b.get_x() + b.get_width()/2, v, f"{v:,}\n({100*v/len(df):.1f}%)",
                ha="center", va="bottom", fontsize=9)
    save(fig, "22_completeness_distribution")

    # Top 20 universities by avg completeness
    uni_cc = (big.groupby(["subdomain", "university_name"])["completeness"].mean()
              .sort_values(ascending=False).head(TOP_N_UNI))
    fig, ax = plt.subplots(figsize=(11, 8))
    lbls = [f"{shorten(n, 38)}  [{sd}]" for (sd, n) in uni_cc.index]
    ax.barh(lbls, uni_cc.values, color=PALETTE[12])
    ax.invert_yaxis(); ax.set_xlabel("Avg profile completeness (0–3)")
    ax.set_title(f"Top {TOP_N_UNI} universities by avg profile-completeness score")
    for i, v in enumerate(uni_cc.values):
        ax.text(v, i, f" {v:.2f}", va="center", fontsize=9)
    save(fig, "23_top_universities_by_completeness")

    # === Author Rank & Bragworthy ===
    print("\n[Author rank & bragworthy]")

    ranked = df[(df["author_rank"].notna()) & (df["author_rank"] > 1)]
    if len(ranked):
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.hist(ranked["author_rank"], bins=40, color=PRIMARY, edgecolor="white")
        ax.set_title(f"Distribution of author_rank (excluding rank=1 floor) — n={len(ranked):,}")
        ax.set_xlabel("author_rank"); ax.set_ylabel("# researchers")
        save(fig, "24_author_rank_distribution")

    # Bragworthy per university — absolute and share
    bw = big[big["bragworthy"]].groupby(["subdomain", "university_name"]).size().sort_values(ascending=False)
    top_bw = bw.head(TOP_N_UNI)
    if len(top_bw):
        fig, ax = plt.subplots(figsize=(11, 8))
        lbls = [f"{shorten(n, 38)}  [{sd}]" for (sd, n) in top_bw.index]
        ax.barh(lbls, top_bw.values, color=ACCENT)
        ax.invert_yaxis(); ax.set_xlabel("# bragworthy researchers")
        ax.set_title(f"Top {TOP_N_UNI} universities by absolute count of bragworthy researchers")
        for i, v in enumerate(top_bw.values):
            ax.text(v, i, f" {int(v)}", va="center", fontsize=9)
        save(fig, "25_bragworthy_absolute_by_university")

        bw_share = (big.groupby(["subdomain", "university_name"])["bragworthy"].mean() * 100
                    ).sort_values(ascending=False).head(TOP_N_UNI)
        fig, ax = plt.subplots(figsize=(11, 8))
        lbls = [f"{shorten(n, 38)}  [{sd}]" for (sd, n) in bw_share.index]
        ax.barh(lbls, bw_share.values, color="#9b59b6")
        ax.invert_yaxis(); ax.set_xlabel("% bragworthy researchers")
        ax.set_title(f"Top {TOP_N_UNI} universities by *share* of bragworthy researchers")
        for i, v in enumerate(bw_share.values):
            ax.text(v, i, f" {v:.2f}%", va="center", fontsize=9)
        save(fig, "26_bragworthy_share_by_university")

    # Top 25 bragworthy researchers
    brag_top = df[df["bragworthy"]].nlargest(25, "followers_count")
    if len(brag_top):
        fig, ax = plt.subplots(figsize=(12, 9))
        labels = [f"{shorten(r.display_name, 28)} @ {shorten(r.university_name, 22)}"
                  for r in brag_top.itertuples()]
        ax.barh(labels, brag_top["followers_count"], color=ACCENT)
        ax.invert_yaxis(); ax.set_xlabel("Followers")
        ax.set_title("Top 25 bragworthy researchers — by followers (papers / rank annotated)")
        for i, r in enumerate(brag_top.itertuples()):
            ax.text(r.followers_count, i,
                    f"  {int(r.followers_count):,} f / {int(r.papers_count):,} pap / rank {r.author_rank:.1f}",
                    va="center", fontsize=8)
        save(fig, "27_top_bragworthy_researchers")

    # === University comparative ===
    print("\n[University comparative]")

    uni_agg = (big.groupby(["subdomain", "university_name"])
               .agg(n=("user_id", "size"),
                    avg_followers=("followers_count", "mean"),
                    avg_papers=("papers_count", "mean"),
                    share_paper=("papers_count", lambda x: (x >= 1).mean() * 100),
                    completeness=("completeness", "mean"),
                    pct_bragworthy=("bragworthy", lambda x: x.mean() * 100))
               .reset_index())
    label_lookup = uni_agg.nlargest(30, "n")

    def label_scatter(ax, df_lab, x_col, y_col):
        for _, r in df_lab.iterrows():
            ax.annotate(r["subdomain"], (r[x_col], r[y_col]),
                        fontsize=7, alpha=0.85, color="#444")

    # Headcount vs avg followers
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(uni_agg["n"], uni_agg["avg_followers"], s=40, alpha=0.5, color=PRIMARY)
    ax.set_xscale("log"); ax.set_yscale("log")
    label_scatter(ax, label_lookup, "n", "avg_followers")
    ax.set_xlabel("# researchers (log)"); ax.set_ylabel("Avg followers per researcher (log)")
    ax.set_title("University headcount vs avg follower count (top 30 labelled)")
    save(fig, "28_headcount_vs_avg_followers")

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(uni_agg["n"], uni_agg["share_paper"], s=40, alpha=0.5, color=PALETTE[4])
    ax.set_xscale("log")
    label_scatter(ax, label_lookup, "n", "share_paper")
    ax.set_xlabel("# researchers (log)"); ax.set_ylabel("% researchers with ≥1 paper")
    ax.set_title("University headcount vs % of researchers with ≥1 paper")
    save(fig, "29_headcount_vs_paper_share")

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(uni_agg["n"], uni_agg["completeness"], s=40, alpha=0.5, color=PALETTE[8])
    ax.set_xscale("log")
    label_scatter(ax, label_lookup, "n", "completeness")
    ax.set_xlabel("# researchers (log)"); ax.set_ylabel("Avg profile-completeness (0–3)")
    ax.set_title("University headcount vs profile-completeness")
    save(fig, "30_headcount_vs_completeness")

    # Heatmap: top 15 universities × metrics (z-scored within column for readability)
    top15 = uni_agg.nlargest(15, "n").copy()
    metric_cols = ["avg_followers", "avg_papers", "share_paper", "completeness", "pct_bragworthy"]
    heat = top15.set_index("subdomain")[metric_cols]
    heat_z = (heat - heat.mean()) / heat.std()
    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(heat_z, annot=heat.round(2), fmt="", cmap="crest",
                cbar_kws={"label": "z-score within column"}, ax=ax)
    ax.set_title("Top 15 universities by headcount — engagement & completeness (heat = z-score, label = raw)")
    save(fig, "31_university_metrics_heatmap")

    # Academic Visibility Index
    av_z = pd.DataFrame({
        "z_avg_followers": (uni_agg["avg_followers"] - uni_agg["avg_followers"].mean()) / uni_agg["avg_followers"].std(),
        "z_avg_papers":    (uni_agg["avg_papers"] - uni_agg["avg_papers"].mean()) / uni_agg["avg_papers"].std(),
        "z_completeness":  (uni_agg["completeness"] - uni_agg["completeness"].mean()) / uni_agg["completeness"].std(),
    })
    uni_agg["AVI"] = av_z.sum(axis=1)
    avi_top = uni_agg.nlargest(TOP_N_UNI, "AVI")
    fig, ax = plt.subplots(figsize=(11, 8))
    lbls = [f"{shorten(r.university_name, 38)}  [{r.subdomain}]" for r in avi_top.itertuples()]
    ax.barh(lbls, avi_top["AVI"], color=PRIMARY)
    ax.invert_yaxis(); ax.set_xlabel("Academic Visibility Index (z-sum of follower + paper + completeness)")
    ax.set_title(f"Top {TOP_N_UNI} universities by composite Academic Visibility Index")
    for i, v in enumerate(avi_top["AVI"]):
        ax.text(v, i, f" {v:+.2f}", va="center", fontsize=9)
    save(fig, "32_academic_visibility_index")

    # === Department-level (top universities) ===
    print("\n[Department comparative]")

    dep_agg = (big.groupby(["university_name", "department_name"])
               .agg(n=("user_id", "size"),
                    avg_followers=("followers_count", "mean"),
                    avg_papers=("papers_count", "mean"),
                    share_paper=("papers_count", lambda x: (x >= 1).mean() * 100))
               .reset_index())
    # Top 25 departments by count (already done above as 04), do by avg_followers / share_paper
    dep_top_fol = (dep_agg[dep_agg["n"] >= 50]
                   .nlargest(25, "avg_followers"))
    fig, ax = plt.subplots(figsize=(11, 9))
    lbls = [f"{shorten(r.department_name, 32)} @ {shorten(r.university_name, 22)}"
            for r in dep_top_fol.itertuples()]
    ax.barh(lbls, dep_top_fol["avg_followers"], color=PALETTE[11])
    ax.invert_yaxis(); ax.set_xlabel("Avg followers per researcher")
    ax.set_title("Top 25 departments by avg follower count (depts with ≥50 researchers)")
    for i, v in enumerate(dep_top_fol["avg_followers"]):
        ax.text(v, i, f" {v:.1f}", va="center", fontsize=8)
    save(fig, "33_top_departments_by_avg_followers")

    dep_top_pap = (dep_agg[dep_agg["n"] >= 50]
                   .nlargest(25, "share_paper"))
    fig, ax = plt.subplots(figsize=(11, 9))
    lbls = [f"{shorten(r.department_name, 32)} @ {shorten(r.university_name, 22)}"
            for r in dep_top_pap.itertuples()]
    ax.barh(lbls, dep_top_pap["share_paper"], color=PALETTE[6])
    ax.invert_yaxis(); ax.set_xlabel("% with ≥1 paper")
    ax.set_title("Top 25 departments by paper-publication rate (depts with ≥50 researchers)")
    for i, v in enumerate(dep_top_pap["share_paper"]):
        ax.text(v, i, f" {v:.1f}%", va="center", fontsize=8)
    save(fig, "34_top_departments_by_paper_share")

    # Heatmap dept × {avg followers, avg papers} for top 20 by size
    dep_top20 = dep_agg.nlargest(20, "n").copy()
    dep_top20["label"] = [f"{shorten(r.department_name, 28)} @ {shorten(r.university_name, 18)}"
                          for r in dep_top20.itertuples()]
    heat = dep_top20.set_index("label")[["avg_followers", "avg_papers", "share_paper"]]
    heat_z = (heat - heat.mean()) / heat.std()
    fig, ax = plt.subplots(figsize=(8, 9))
    sns.heatmap(heat_z, annot=heat.round(2), fmt="", cmap="crest",
                cbar_kws={"label": "z-score within column"}, ax=ax)
    ax.set_title("Top 20 departments by size — engagement metrics (heat = z, label = raw)")
    save(fig, "35_department_metrics_heatmap")

    # === Geography ===
    print("\n[Geography]")

    co = df["country"].value_counts()
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(co.index, co.values, color=PRIMARY)
    ax.invert_yaxis()
    ax.set_xlabel("Researchers")
    ax.set_title("Researchers by inferred country (from subdomain TLD suffix)")
    for i, v in enumerate(co.values):
        ax.text(v, i, f" {v:,}", va="center", fontsize=9)
    save(fig, "36_researchers_by_country")

    co_eng = df.groupby("country").agg(
        avg_followers=("followers_count", "mean"),
        avg_papers=("papers_count", "mean"),
        share_paper=("papers_count", lambda x: (x >= 1).mean() * 100),
    ).loc[co.index]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    for ax, col, title in zip(
        axes,
        ["avg_followers", "avg_papers", "share_paper"],
        ["Avg followers", "Avg papers", "% with ≥1 paper"],
    ):
        ax.barh(co_eng.index, co_eng[col], color=PRIMARY)
        ax.set_title(title); ax.invert_yaxis()
    fig.suptitle("Engagement by inferred country")
    save(fig, "37_engagement_by_country")

    # === Network / Relational ===
    print("\n[Network / relational]")

    # University × dept-keyword bipartite heatmap
    KEYWORDS = ["Economic", "Business", "Law", "Engineering", "Computer", "Education",
                "Mathematic", "Physics", "Chemistry", "Biolog", "Medic",
                "History", "Sociol", "Psycholog", "Philosoph"]
    big["dept_kw"] = "Other"
    for kw in KEYWORDS:
        mask = big["department_name"].astype(str).str.contains(kw, case=False, na=False)
        big.loc[mask & (big["dept_kw"] == "Other"), "dept_kw"] = kw
    top15_uni = uni_n.head(15)["subdomain"].tolist()
    bb = big[big["subdomain"].isin(top15_uni)]
    mat = (bb.groupby(["subdomain", "dept_kw"]).size()
           .unstack(fill_value=0).reindex(index=top15_uni))
    mat = mat[KEYWORDS + ["Other"]]
    fig, ax = plt.subplots(figsize=(12, 7))
    sns.heatmap(mat, annot=True, fmt="d", cmap="crest", ax=ax,
                cbar_kws={"label": "# researchers"})
    ax.set_title("Top 15 universities × department-name keyword (researchers)")
    ax.set_xlabel("Department keyword"); ax.set_ylabel("University subdomain")
    save(fig, "38_university_x_dept_keyword_heatmap")

    # Followers vs Following scatter (log-log) — all researchers with both > 0
    sub_fg = df[(df["followers_count"] > 0) & (df["following_count"] > 0)]
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(sub_fg["following_count"], sub_fg["followers_count"],
               s=3, alpha=0.1, color=PRIMARY)
    ax.set_xscale("log"); ax.set_yscale("log")
    lim = max(sub_fg["following_count"].max(), sub_fg["followers_count"].max())
    ax.plot([1, lim], [1, lim], "--", color=ACCENT, alpha=0.6, label="follow ≡ followed")
    ax.set_xlabel("Following (log)"); ax.set_ylabel("Followers (log)")
    ax.set_title("Followers vs Following — reciprocal-attention landscape")
    ax.legend()
    save(fig, "39_followers_vs_following_scatter")

    print(f"\nGenerated {len(list(OUT.glob('*.png')))} charts in {OUT}/")


if __name__ == "__main__":
    main()
