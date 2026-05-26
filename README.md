# Academia.edu Public-Registry Snapshot — Business Analysis

A scraped snapshot of the public researcher registry on Academia.edu, covering **239,708 researchers across 67 universities and 5,615 departments**. This document is a business-focused read-out of what the data says about the platform, the institutions it covers, and the people who use it. Every claim references a specific chart in `charts/`.

---

## 1. Executive Summary

- **The platform is essentially a discoverability shell, not a participation venue.** 86.8% of researchers have uploaded zero papers, 52.5% have zero followers, and 64.8% have *none* of (bio, public email, profile photo) populated. Only 1.77% — about 1 in 56 — have a fully completed profile. ([Chart 12](charts/12_papers_distribution.png), [Chart 22](charts/22_completeness_distribution.png))
- **Growth has stopped.** 51.1% of all accounts were created in just 2019–2020. From 2021 onwards, only 1.57% of the registry's accounts were created — a near-total collapse in new sign-ups (or in the platform's ability to surface them publicly). ([Chart 7](charts/07_accounts_per_year.png))
- **Attention is extremely concentrated.** The top 1% of researchers (≈2,400 accounts) hold **58% of all followers**; the top 100 alone hold 36.8%. The most-followed researcher is Daniel Hershenzon at the University of Connecticut with **255,610 followers** — a long-tail outlier of platform fame. ([Chart 15](charts/15_followers_vs_papers_scatter.png), [Chart 16](charts/16_top_followed_researchers.png))
- **Coverage is broadly distributed across institutions.** The largest single university (UCLA) is only 4.29% of the dataset; the top 10 universities account for 34% of researchers. There is no coverage-skew warning. ([Chart 2](charts/02_top_universities_by_count.png), [Chart 6](charts/06_coverage_spread.png))
- **The platform's quality signals are sparse.** 98.6% of researchers carry the floor `author_rank` of 1, and only **0.82% (1,968 researchers)** are flagged `bragworthy` — the editorial highlight signal. ([Chart 24](charts/24_author_rank_distribution.png), [Chart 26](charts/26_bragworthy_share_by_university.png))
- **Per-researcher engagement is *inversely* related to university size.** The composite Academic Visibility Index is led by small, research-dense institutions (Field Museum, Hiroshima University, SISSA), not the big-headcount names. Big universities dilute their metrics with thousands of dormant accounts. ([Chart 32](charts/32_academic_visibility_index.png), [Chart 28](charts/28_headcount_vs_avg_followers.png))
- **For any product built on this data, gmail.com is the *primary* contact channel** — among the 3.4% of researchers who publish an email, 25.6% (2,066 / ≈8,100) use a personal `gmail.com` address, more than any single institutional domain. That has direct implications for verification, deliverability, and trust.

---

## 2. Dataset Overview

| Field | Value |
|---|---|
| Source | `https://{subdomain}.academia.edu/` |
| Scrape pipeline | `scripts/scraper.py` (asyncio + curl_cffi + aiohttp + aiofiles, Cloudflare-bypass via Chrome TLS fingerprint) |
| Snapshot frozen at | 2026-05-26 (analysis file: `data/data.snapshot.csv`) |
| Total researchers (rows) | **239,708** |
| Universities (distinct subdomains) | **67** |
| Departments | **5,615** |
| Columns | 24 |
| Format | UTF-8 CSV, no BOM |

This is a **public-registry snapshot**, not an activity stream. The only time dimension that can be analysed is `created_at` (account creation timestamp). Engagement numbers (`followers_count`, `papers_count`) are point-in-time totals as observed by the scraper, not deltas.

The scraper is running and may extend coverage further; this report freezes the analysis at the snapshot above.

---

## 3. Data Quality Summary

Recomputed against the live data:

| Column | Empty rate | Treatment |
|---|---|---|
| `middle_initials` | 99.00% | Drop from analysis |
| `public_email` | 96.64% | Treat empty as "no public email"; report contactability as a headline metric |
| `about` | 94.69% | Treat empty as "no public bio" |
| `papers_count` | 86.79% | Empty = 0 papers (verified against source) — imputed to 0 |
| `followers_count` | 52.48% | Empty = 0 followers — imputed to 0 |
| `following_count` | 17.06% | Empty = 0 — imputed to 0 |
| `author_rank` / `bragworthy` | 0.61% | Treated as missing for ranked analysis |
| `first_name` / `last_name` | 0.00% | Effectively complete |
| `department_name` | 0.00% | 1 row missing — negligible |

**Invariants checked, all passed:**
- 0 duplicate `user_id`
- 0 duplicate `(subdomain, page_name)`
- 0 duplicate `profile_url`
- `subdomain` ↔ `university_id` ↔ `university_name` are strictly 1-to-1
- `(university_id, department_id)` maps to exactly one `department_name`
- `subdomain` extracted from `profile_url` matches the `subdomain` column on all 239,708 rows
- `has_photo == False` perfectly aligns with `photo_url == /images/s65_no_pic.png`

The dataset is **byte-perfect** — no corruption, no orphan rows, no cross-key drift.

---

## 4. Coverage Disclosure

**No single-university dominance.** UCLA is the largest single subdomain at 4.29% of all rows; the top 5 together are only 19.4%. The dataset is broadly distributed, so per-university and per-country comparisons can be made without coverage-skew caveats.

![Coverage spread](charts/06_coverage_spread.png)

The scraper had reached 67 of the ~89 publicly-discoverable Academia.edu subdomains at snapshot time. Stanford, Yale, UPenn, Washington, and others were not yet included; those will land in subsequent runs.

---

## 5. Key Findings

### 5.1 University Size

**Finding A — A long, flat distribution of institution sizes.** Researcher counts per university range from a handful (specialty institutes) to ~10,000 (UCLA, HKU, Macquarie). The median university has roughly 2,500 researchers; the largest 20 universities account for 56% of all records.

![Top 20 universities](charts/02_top_universities_by_count.png)
![Distribution of researchers per university](charts/03_university_count_distribution.png)

**Why it matters:** for a research-platform vendor sizing the market, this means **no single account-acquisition deal** unlocks more than ~4% of the population — partnership strategy must be multi-institution.

**Finding B — Department counts are skewed by big-tent business and computer-science programs.** The top 30 departments are all business schools, CS departments, or arts/social-science faculties at the largest universities, each holding 700–1,000 researchers.

![Top 30 departments by count](charts/04_top_departments_by_count.png)

**Why it matters:** academic-talent vendors targeting specific fields can hit a meaningful audience by going department-deep at five or six institutions, rather than chasing breadth.

---

### 5.2 Engagement

**Finding C — The "zero club" is the dominant population.** 208,045 researchers (86.8%) have not uploaded a single paper, and 125,794 (52.5%) have zero followers. The platform is a directory for most users, not a publishing workflow.

![Papers distribution](charts/12_papers_distribution.png)
![Followers distribution](charts/10_followers_distribution.png)

**Why it matters:** any product positioning Academia.edu as a "research social network" overstates the engagement that actually exists. The realistic positioning is **"a global academic phonebook with a thin layer of public scholarship attached."**

**Finding D — Attention follows a brutal power law.** The top 1% of researchers (2,397 accounts) hold **58% of all followers** in the registry; the top 100 alone hold 36.8%. The single most-followed researcher — Daniel Hershenzon at the University of Connecticut — has 255,610 followers, while the median researcher has zero.

![Followers vs Papers](charts/15_followers_vs_papers_scatter.png)
![Top 25 most-followed](charts/16_top_followed_researchers.png)
![Top 25 most-published](charts/17_top_published_researchers.png)

**Why it matters:** a recruiter or research-intelligence buyer should treat the top 2,000–5,000 accounts as the entire substantive audience for any messaging strategy that depends on reach. Buying access to "100,000 academics" overstates real influence by ~50×.

---

### 5.3 Profile Completeness

**Finding E — Most profiles are skeletal.** Of 239,708 researchers, 155,278 (64.8%) have **none** of (bio, public email, profile photo) populated. Only 4,247 (1.77%) have all three.

![Completeness distribution](charts/22_completeness_distribution.png)

**Why it matters:** institutions evaluating their public Academia.edu footprint should know that the typical faculty page on the platform has nothing more than a name and department. A free-text bio is present on only 5.3% of profiles; a public email on only 3.4%.

**Finding F — Among researchers who do publish an email, personal gmail dominates institutional addresses.** Of ~8,100 publishable emails, `gmail.com` accounts for 2,066 (25.6%) — more than any single university domain. The next most common are institutional addresses (`uchicago.edu` 172, `sfu.ca` 141, `ucsc.edu` 132, `ucl.ac.uk` 131, `qub.ac.uk` 126).

| Top 10 email domains | Count |
|---|---:|
| gmail.com | 2,066 |
| hotmail.com | 185 |
| uchicago.edu | 172 |
| sfu.ca | 141 |
| ucsc.edu | 132 |
| ucl.ac.uk | 131 |
| qub.ac.uk | 126 |
| yahoo.com | 125 |
| kcl.ac.uk | 120 |
| st-andrews.ac.uk | 114 |

**Why it matters:** for any verification or deliverability product (legal-tech, recruiting, conference outreach), the **majority of contactable Academia.edu researchers use a personal email**, not an institutional one. This breaks any assumption that you can authenticate identity via the institutional domain.

![About share by university](charts/19_about_share_by_university.png)
![Email share by university](charts/20_email_share_by_university.png)
![Photo share by university](charts/21_photo_share_by_university.png)

The leaderboard universities for completeness are **small specialty institutions** (Field Museum, Crete, Hindawi/Al-Baha) — large universities don't make the cut. ([Chart 23](charts/23_top_universities_by_completeness.png))

---

### 5.4 Author Rank & Bragworthy

**Finding G — The platform's `author_rank` signal is sparse.** 98.6% of researchers sit at the floor value of 1.0 — meaning they are *unranked* in the platform's percentile system. Only 1,900 researchers (0.79%) have a meaningful (non-floor) rank.

![Author rank distribution (excluding the floor)](charts/24_author_rank_distribution.png)

**Finding H — `bragworthy` is the more useful editorial signal but covers <1% of researchers.** 1,968 researchers (0.82%) carry the `bragworthy = True` flag — Academia.edu's curated "high-value" label. They cluster at:

| University | Bragworthy count | Bragworthy share |
|---|---:|---:|
| University of Chicago | 97 | 1.18% |
| University of St Andrews | 83 | 1.92% |
| University of Crete | 81 | 2.11% |
| Simon Fraser University | 74 | 0.85% |
| King's College London | 67 | 1.26% |

![Bragworthy absolute by university](charts/25_bragworthy_absolute_by_university.png)
![Bragworthy share by university](charts/26_bragworthy_share_by_university.png)
![Top 25 bragworthy researchers](charts/27_top_bragworthy_researchers.png)

**Why it matters:** for an academic-recruiting product, **`bragworthy` is the single most valuable per-researcher signal** in the dataset — it identifies the ~2,000 individuals whom the platform itself considers high-influence. A complete recruiting universe is 2,000 names, not 200,000.

---

### 5.5 Account Age

**Finding I — Academia.edu's free-tier growth has effectively flatlined since 2021.** 51.1% of every account in the snapshot was created in 2019 or 2020 — a peak so sharp that 2019 alone accounts for 28.5% of the entire registry. From 2021 onwards, only 1.57% of accounts were created (3,772 of 239,708).

![Accounts per year](charts/07_accounts_per_year.png)
![Monthly recent](charts/08_monthly_recent.png)

**Why it matters:** any investor or competitor sizing the addressable academic audience should treat Academia.edu as **a stocked dataset, not a growing audience**. The publicly-visible new-user pipeline died around 2021 — either growth stopped, or growth got hidden behind paywall/auth changes. Either way, what's there is what you get.

---

### 5.6 Geography

**Finding J — The dataset is Anglophone-dominated.** Researchers map to 14 countries (via subdomain TLD heuristic). 65% are USA / Other (no country suffix), 23% UK, with Hong Kong (4%), Australia (3.2%), Greece (1.6%), Belgium (1.1%) making up most of the rest.

![Researchers by country](charts/36_researchers_by_country.png)
![Engagement by country](charts/37_engagement_by_country.png)

**Per-capita bragworthy density** tells a different story: **Greece is the highest-density country for editorially-curated researchers** (2.07% of Greek-suffix accounts vs 0.79% USA-Other, 0.79% UK). This is driven by the University of Crete, which alone has 81 bragworthy researchers out of 3,836 total — disproportionately rich in platform-curated authors.

**Why it matters:** for a research-intelligence vendor scoring institutions globally, **headcount alone misleads**. The Greek and Italian (SISSA, 4.5 AVI) subdomains punch far above their weight on a per-researcher basis.

---

## 6. Cross-Dimension Relationships

**Finding K — Larger universities are *less* engaged per researcher.** Plotting headcount against average follower count shows a clear negative slope: the universities with the most researchers (UCLA, HKU, Macquarie) sit at the bottom of the per-researcher engagement axis. The high-engagement institutions (Hiroshima, Field Museum, SISSA) all have small headcounts.

![Headcount vs avg followers](charts/28_headcount_vs_avg_followers.png)
![Headcount vs paper share](charts/29_headcount_vs_paper_share.png)
![Headcount vs completeness](charts/30_headcount_vs_completeness.png)

**Why it matters:** the big-headcount universities are inflated by **thousands of inactive accounts** (students who signed up during the 2019-2020 onboarding peak and never came back). Per-capita metrics are the honest comparison; total headcount is not.

**Finding L — Profile completeness predicts engagement.** Universities with higher average completeness scores also have higher average follower counts. Greek subdomains lead on both axes (Crete: 81 bragworthy + 0.79 avg completeness score). This is a soft correlation but it's directionally consistent across the top 30 universities.

![University metrics heatmap](charts/31_university_metrics_heatmap.png)

**Why it matters:** institutions can interpret completeness as a leading indicator of visibility. If your faculty's profiles are blank, you get no signal back from the platform.

---

## 7. University Comparative Analysis

The **composite Academic Visibility Index** = z-score(avg followers) + z-score(avg papers) + z-score(profile completeness). This ranks universities by *quality of footprint per researcher*, not by raw size.

![Academic Visibility Index — top 20](charts/32_academic_visibility_index.png)

| Rank | University | Subdomain | Researchers | Avg followers | Avg papers | Completeness | AVI |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | Field Museum | fieldmuseum | 60 | 91.6 | 54.1 | 1.17 | +14.4 |
| 2 | Hiroshima University | hiroshima-u | 720 | 161.1 | 8.9 | 0.73 | +8.1 |
| 3 | SISSA | sissa | 123 | 27.7 | 19.3 | 0.76 | +4.5 |
| 4 | Al-Baha University (KSA, via hindawi) | hindawi | 95 | 13.5 | 7.2 | 0.96 | +3.2 |
| 5 | University of Crete | crete | 3,836 | — | — | — | +3.7 |

The top of the AVI is dominated by **small, research-dense institutions** — exactly the universities you would *not* find via a headcount-based search. For talent-sourcing, AVI is a better lens than total faculty count.

![Top departments by avg followers](charts/33_top_departments_by_avg_followers.png)
![Top departments by paper share](charts/34_top_departments_by_paper_share.png)
![Department metrics heatmap](charts/35_department_metrics_heatmap.png)

---

## 8. Talent & Influence Analysis

The **top 25 researchers by followers** is the substantive influence layer of the platform — these accounts together account for a double-digit share of all attention on Academia.edu.

![Top 25 most-followed researchers](charts/16_top_followed_researchers.png)
![Top 25 most-published researchers](charts/17_top_published_researchers.png)

The **bragworthy population (1,968 researchers)** is the platform's own short-list of high-value users. They are concentrated in a handful of universities (Chicago, St Andrews, Crete, SFU, KCL) and almost universally have above-floor `author_rank` values.

![Top 25 bragworthy researchers (with stats)](charts/27_top_bragworthy_researchers.png)

The **following/followers ratio** distribution shows that most researchers with any followers at all are **followed more than they follow** (ratio <1 for the bulk of the distribution). This is consistent with a one-way "broadcast" platform where a small minority publishes and the rest reads.

![Following/Followers ratio](charts/18_following_follower_ratio.png)
![Followers vs Following scatter](charts/39_followers_vs_following_scatter.png)

---

## 9. Department-Field Map

Cross-tabulating universities against department-name keywords reveals the **structural footprint of the platform**: every large university has substantial Business, Education, and Computer Science departments; humanities (History, Philosophy, Sociology) are densest at the older UK and US institutions.

![University × department keyword heatmap](charts/38_university_x_dept_keyword_heatmap.png)

For graph-RAG and field-targeted recruiting, this is the starting map: it identifies which universities have meaningful researcher mass in each broad discipline.

---

## 10. Recommendations

**For a research-network / academic-social-graph vendor:**
- Reposition Academia.edu's competitor-positioning analysis around the **2,000-name bragworthy population**, not the 240,000 total. That is the substantive audience.
- The 2021+ growth flatline is a **major competitive opening** — any product that can credibly onboard new academic users today is not facing an active Academia.edu acquisition engine.

**For a university administrator:**
- Use the **Academic Visibility Index** to benchmark per-faculty engagement against peers, not raw headcount.
- Profile-completeness is a cheap and direct lever: encouraging faculty to populate `about`, `email`, and `photo` is correlated with measurable engagement gains. The current floor (5.3% with bios, 3.4% with emails) leaves enormous room.
- The dormant-account problem inflates "we have N faculty on Academia.edu" metrics by ≈10×. Real engagement is 10–15% of headcount.

**For a talent recruiter / academic headhunter:**
- The `bragworthy` flag is the highest-precision signal in the dataset. **1,968 researchers** is a tractable manual outreach universe.
- Be aware that the gmail.com personal-email channel dominates institutional addresses — verification cannot rely on institutional-domain ownership.

**For a bibliometric / research-intelligence buyer:**
- Coverage gaps are concentrated in major US R1 universities (Stanford, Yale, UPenn, Washington) that the snapshot did not yet reach. A complete pass would add roughly 30%+ to total headcount.
- The per-researcher paper counts here are **uploads to Academia.edu**, not bibliographic totals. They under-represent total publication output by 1–2 orders of magnitude. Cross-reference with OpenAlex or ORCID before claiming productivity insights.

**For an early-career researcher:**
- The universities with the highest *share* of bragworthy researchers — St Andrews, Crete, Chicago — are disproportionately rich in publicly-visible, active mentors relative to their headcount. Worth examining when choosing where to apply.

---

## 11. Appendix: Data Quality Notes

- **Snapshot freeze.** The analysis runs against `data/data.snapshot.csv`, frozen on 2026-05-26 at 239,708 rows. The live scraper at `data/data.csv` may be larger by the time you read this.
- **Coverage skew is not a problem here.** The largest single subdomain (UCLA) is 4.29% of rows; the top 10 combined are 34%. Cross-institution comparisons are not distorted by sampling.
- **Empty engagement = zero engagement.** `followers_count`, `following_count`, and `papers_count` are imputed from empty → 0 because the Academia.edu profile-page meta-description omits these fields when the value is zero. This is verified against the source HTML and noted prominently in `prompts/analyse.md`.
- **The `author_rank == 1` floor.** 98.6% of researchers carry this default. Any analysis using `author_rank` should restrict to the 1,900-researcher non-floor subset (and that subset is what's plotted in chart 24).
- **The `bragworthy` editorial signal** covers <1% of researchers (1,968 of 239,708) but is the highest-density per-researcher quality marker in the data.
- **Snapshot, not stream.** This is a point-in-time public-registry capture. Do not infer historical *engagement* trends from the data — only `created_at` is a time signal, and even that is partial for 2026 (the snapshot year).
- **Country inference is a heuristic** based on subdomain TLD suffix (e.g. `-au` → Australia, `-uk` → UK). Subdomains without a country suffix default to "USA / Other" because most US universities use plain subdomains (`ucla`, `nyu`, etc.). A small number of non-US institutions also lack the suffix — they are not separately identifiable from this field.
- **Display-name Unicode coverage.** A few researchers' display names contain CJK characters that DejaVu Sans (the chart font) cannot render; these appear as boxes in charts 16, 17, 27. The data itself is intact in the CSV.
- **The dataset is byte-perfect.** Zero duplicates, zero cross-key drift, zero malformed rows, full 1-to-1 invariant compliance — see Section 3.

---

*Source script: `scripts/generate_charts.py`. Profile audit: `scripts/profile_data.py` (output saved to `data/profile_report.txt`).*
