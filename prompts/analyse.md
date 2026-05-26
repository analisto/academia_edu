Analyze `data/data.csv` with a strict focus on business value and decision-making insights, rather than technical or statistical explanations.

The data is scraped from Academia.edu and represents the public registry of researchers (faculty, postgraduates, independent scholars) affiliated with university subdomains on the platform — captured via `scripts/scraper.py`.

## Dataset

| File | Records | Description | Key columns |
|------|---------|-------------|-------------|
| `data.csv` | ~thousands (one row per researcher) | Public registry of every researcher discoverable through each university's `/Departments/` listings on Academia.edu | `subdomain`, `university_id`, `university_name`, `department_id`, `department_name`, `user_id`, `display_name`, `created_at`, `followers_count`, `following_count`, `papers_count`, `about`, `public_email`, `author_rank`, `bragworthy`, `has_photo` |

**Full column list (24):** `subdomain, university_id, university_name, department_id, department_name, department_url, user_id, page_name, display_name, first_name, middle_initials, last_name, profile_url, photo_url, has_photo, created_at, followers_count, following_count, papers_count, about, public_email, author_rank, bragworthy, scraped_at`.

**Provenance:** the row count and per-university coverage depend on when the scraper was run and whether the run completed. The scraper is resumable; `scraped_at` reflects the time each row was written. Treat `data.csv` as a public-registry snapshot, not a time series of activity.

**Natural keys:** `user_id` is the platform-wide primary key. `(university_id, department_id)` is the parent context. The same researcher can in principle be re-encountered through multiple departments, but the scraper deduplicates by `user_id` in-memory and the recovery path scans `data.csv` itself, so duplicates should not appear; the profiling step must still verify this.

## Known Data Quality Issues (verified on the current sample)

Percentages below are taken from a partial sample (~3,800 rows, heavily weighted to one university). The Step 0 profiling step MUST recompute exact rates against the live `data/data.csv`. Use these as expected magnitudes, not as ground truth.

| Issue | Observed in sample | Handling |
|-------|--------------------|----------|
| `about` field empty | ~95% empty | Treat empty as "no public bio". Analyze the populated subset only. Do not impute. |
| `public_email` empty | ~97% empty | Treat empty as "no public email". Report contactability rate as a headline metric — it is one of the few hard product signals in the data. |
| `papers_count` empty | ~92% empty | The meta-description on the profile page only mentions papers when the user has uploaded at least one. Treat empty as **0 papers** (verified against source HTML). Recompute distribution accordingly. |
| `followers_count` empty | ~58% empty | Empty means the meta-description did not include a "Followers" segment, which happens when the count is 0. Treat empty as **0 followers**. |
| `following_count` empty | ~16% empty | Same logic — treat empty as **0 following**. |
| `middle_initials` empty | ~99% empty | Drop from analysis. Optional bio field, almost never used. |
| `photo_url == /images/s65_no_pic.png` | ~71% of rows | This is the default placeholder. Equivalent to `has_photo == False`. Use `has_photo` as the boolean; ignore `photo_url` for analysis except possibly as an engagement signal. |
| `author_rank == 1` for ~99% of rows | Most users are at the floor of the platform's percentile ranking | Treat rank=1 as "unranked / baseline". The handful with non-integer ranks (e.g. 2.04, 3.34) are the actually-ranked authors and deserve a separate slice. |
| `bragworthy == True` for <1% of rows | Academia.edu's editorially-curated highlight flag | Use as a quality signal — these are the platform's top-of-distribution researchers. |
| `display_name` contains Azerbaijani / Turkish / Cyrillic / CJK / accented Latin characters | Multi-script data | Read CSV as UTF-8. Use a font that covers extended Latin + CJK + Cyrillic in charts (e.g. Noto Sans, DejaVu Sans). |
| `department_name` and `university_name` are free-text, sometimes in the native language of the institution (Russian, Azerbaijani, Japanese, etc.) | Cross-institution comparison needs label normalization | Truncate to ~40 chars on chart axes; keep original on hover/tooltips |
| `created_at` spans 2008→present | Academia.edu launched in 2008 | Bucket by year for trend visuals; treat the most recent year as partial (do not extrapolate). |
| One subdomain can dominate the dataset if the scrape is partial | E.g. ~99% of the sample is from one university | Always report counts per subdomain at the top of the profile so the audience knows the coverage shape |

## Step 0: Data Profiling (mandatory before any analysis)

Before generating any charts or insights, run a full data quality audit on `data/data.csv`:

- Row count, column count, file size, encoding (UTF-8, no BOM)
- Duplicate records — by `user_id` (must be unique) and by `(subdomain, page_name)` (must also be unique)
- Missing/empty values per column (count + percentage)
- Cardinality of categorical-style columns (`subdomain`, `university_name`, `department_name`, `bragworthy`, `has_photo`)
- Per-subdomain row counts — **print this first**, since coverage skew is the single biggest threat to honest analysis
- Per-university row counts (sanity-check that `subdomain ↔ university_id ↔ university_name` is consistent — no university appearing under two subdomains, no subdomain mapping to two universities)
- Per-department row counts (top 20, bottom 20)
- Distribution of numeric fields after imputing empty → 0 for `papers_count`, `followers_count`, `following_count`: min, max, mean, median, p25, p75, p90, p99
- Distribution of `author_rank` — flag the count of rows where rank ≠ 1
- Distribution of `bragworthy == True`
- `created_at` distribution by year (and by month for the most recent two years)
- Cross-column consistency checks:
  - `has_photo == False` iff `photo_url == /images/s65_no_pic.png` (catch any drift)
  - `subdomain` extracted from `profile_url` matches the row's `subdomain` column
  - Every `university_id` in the data corresponds to exactly one `university_name` (no name drift)
  - Every `department_id` corresponds to exactly one `department_name` within a single university

Print a summary table to the console. If critical issues are found (`user_id` duplicates, encoding errors, single-subdomain coverage above 95%), flag them at the top of the report so the audience reads insights with the right caveats.

## Step 1: Charts Generation

Create a dedicated directory named `charts/`.

Implement a Python script named `scripts/generate_charts.py` that:

- Reads `data/data.csv` and produces all required visualizations
- Uses only business-appropriate chart types (bar, horizontal bar, stacked bar, line, histogram, heatmap, scatter, boxplot)
- **Do NOT use pie charts under any circumstances**
- Every chart must have a clear title, labeled axes, and readable fonts (min 10pt)
- Use a consistent color palette across all charts
- Save charts as PNG at 150+ DPI for presentation quality
- Handle multi-script display names correctly — install/select a font with broad Unicode coverage (Noto Sans or DejaVu Sans)
- Use `tight_layout()` or `constrained_layout=True` to prevent label clipping
- **After generating all charts, visually verify every single chart for readability.** Open each PNG and check:
  - Labels are not overlapping or cut off
  - Y-axis text is readable (no overlap when many bars)
  - Heatmap cells have legible numbers
  - Legend entries are not truncated beyond recognition
  - Stacked bars actually show meaningful segments
  - Log-scale axes are clearly marked as log-scale
  - If any chart is unreadable, fix it before proceeding (reduce items, shorten labels, increase figure size)
- University names are long ("Azerbaijan State University of Economics (UNEC)") — shorten on axes; consider showing the subdomain as a compact label
- Distributions of `followers_count` / `papers_count` are heavily right-skewed (zero-inflated long tails) — use log-scale or clip the long tail and explicitly show the clipped count
- For any chart aggregating by university, restrict to subdomains with ≥50 rows (to avoid noise from partial scrapes)

### Required chart categories (at minimum):

**Volume & Coverage (anchor the audience first):**
- Record count overview — total researchers, total universities (subdomains with ≥1 row), total departments
- Researchers per university — top 20 (horizontal bar)
- Researchers per university — full distribution (histogram, log-x if needed)
- Researchers per department — top 30 across all universities (horizontal bar, label as "Dept @ University")
- Researchers per department — distribution histogram (bin width 10)
- Coverage warning chart: if any single subdomain accounts for >50% of rows, show it explicitly as a stacked bar of "subdomain X vs all others"

**Account age (registration trend):**
- New researchers added to the platform per year (bar chart, 2008→present)
- Monthly cadence for the last 24 months (line chart) — surfaces seasonality and recent platform activity
- Median account age by university — top 20 universities (which institutions onboarded earliest vs latest?)

**Engagement — Followers / Following / Papers:**
- Followers distribution — histogram (log-y), with annotated median, p90, p99
- Following distribution — histogram (log-y)
- Papers-per-researcher distribution — histogram, with the "0 papers" bar visually distinct
- Share of researchers who have at least 1 paper, by university (top 20)
- Share of researchers with ≥10 followers, by university (top 20)
- Followers vs Papers — scatter, log-log, with top 30 highest-followers researchers labeled
- Top 25 most-followed researchers — horizontal bar (label: `display_name @ university`)
- Top 25 most-published researchers — horizontal bar
- Following / Followers ratio — distribution; flag the "fan vs follower" segments (ratio <0.5 = popular, ratio >2 = curator/seeker)

**Profile completeness / Contactability:**
- Share with `about` populated, by university (top 20)
- Share with `public_email` populated, by university (top 20)
- Share with `has_photo == True`, by university (top 20)
- Composite profile-completeness score (about + email + photo as a 0–3 score) — distribution across all researchers
- Top 20 universities by composite profile-completeness average — this is a proxy for how seriously the institution treats Academia.edu visibility

**Author Rank & Bragworthy:**
- Histogram of `author_rank` excluding the rank=1 floor (i.e. the actually-ranked subset)
- Count of `bragworthy == True` per university (top 20 by absolute count, and top 20 by *share*)
- Top 25 bragworthy researchers — horizontal bar with their followers / papers / rank annotated

**University-level Comparative:**
- Headcount vs average followers per researcher — scatter (top 30 universities labeled)
- Headcount vs share with ≥1 paper — scatter (top 30 universities labeled)
- Headcount vs profile-completeness score — scatter (top 30 universities labeled)
- Heatmap: top 15 universities × {avg followers, avg papers, profile-completeness, % bragworthy}
- Composite "Academic Visibility Index" per university = z-score(avg followers) + z-score(avg papers) + z-score(profile completeness) — ranked horizontal bar of top 20

**Department-level (within the largest universities only):**
- Top 25 departments by researcher count
- Top 25 departments by average followers
- Top 25 departments by share with ≥1 paper
- Heatmap of department × {avg followers, avg papers} for top 20 departments

**Geography (derived from subdomain suffix):**
- Researchers by country/region — use the subdomain TLD heuristic (`-au` → Australia, `-az` → Azerbaijan, `-uk` → UK, `-jp` → Japan, etc.; subdomains without a country suffix → "US / Other"). Always show the "Other / unparsed" bar explicitly.
- Average engagement (followers, papers) by inferred country — bar chart
- Coverage map: country-level researcher counts (treemap or bar — no map required unless geo coordinates are added later)

**Network / Relational signals (for future graph work):**
- University × department bipartite heatmap — top 15 universities × top 15 department-name keywords (Economics, Law, Engineering, etc., after keyword extraction from `department_name`)
- Followers vs Following — scatter, log-log, all researchers (to visualize the reciprocal-attention landscape)

## Step 2: Insights and Findings

Identify key trends, patterns, anomalies, and relationships within the data that are relevant to business stakeholders. Relevant stakeholders for this dataset include:
- A research-network / academic-social-graph vendor (sizing market opportunity, identifying engagement hotspots)
- A university administrator (benchmarking faculty visibility against peers)
- A talent recruiter or academic headhunter (finding high-influence researchers in target fields)
- A bibliometric or research-intelligence company (assessing data-partnership value)
- An early-career researcher choosing where to apply (where are the active mentors with public profiles?)

Requirements:
- Every major insight MUST be directly supported by one or more charts
- Prioritize insights that can influence strategy, operations, market entry, talent acquisition, or product design
- Include at minimum:
  - **2 university-size insights** (e.g., "the top 10 universities account for X% of all researchers in the registry")
  - **2 engagement insights** (e.g., "X% of researchers have zero published papers; the top 1% holds Y% of all followers")
  - **2 contactability/profile-completeness insights** (e.g., "X% of researchers do not publish a public email; among those who do, gmail dominates with Y%")
  - **2 author-rank / bragworthy insights** (e.g., "X researchers are flagged 'bragworthy' — they cluster in N universities and Y departments")
  - **1 account-age / registration-cohort insight** (e.g., "registration peaked in 2019–2020; the platform's growth has flattened since")
  - **1 cross-dimension insight** (e.g., "universities with the highest profile-completeness scores also have the highest average follower counts — visibility correlates with platform investment")
  - **1 geographic insight** (e.g., "Australian-suffix subdomains account for X% of researchers in the registry but Y% of bragworthy authors")
  - **1 anomaly or data-quality insight worth noting** (e.g., "99% of researchers carry the default author_rank=1, meaning the platform's ranking signal is sparse and effectively binary at this scale")
- Quantify everything: use exact numbers, percentages, and comparisons — not vague statements
- Context matters: this is a snapshot of the public registry as of the scrape date, not a time series of activity. Do not infer real-time engagement trends.

## Step 3: README Presentation Document

Document all findings in a `README.md` file at the project root.

The README must be written as a presentation-style narrative for non-technical stakeholders (executives, product owners, university leadership, journalists, research-platform investors).

Structure:
1. **Executive Summary** — 5–7 bullet points with the most impactful findings
2. **Dataset Overview** — what data was scraped, scope, source URL pattern (`https://{subdomain}.academia.edu/`), scrape date, record count, university count, department count. Clarify that this is a public-registry snapshot, not historical activity data.
3. **Data Quality Summary** — brief table showing completeness and any caveats per column (use the known issues table above as a starting point, refresh percentages from the live data)
4. **Coverage Disclosure** — if any single subdomain accounts for >25% of rows, lead with this so the reader interprets every chart correctly
5. **Key Findings** — organized by theme (University Size, Engagement, Profile Completeness, Author Rank, Account Age, Geography), each finding with:
   - What the chart shows (embed chart image)
   - Why it matters to the business
   - What decisions or actions it could inform
6. **Cross-Dimension Relationships** — dedicated section for insights that connect headcount ↔ engagement ↔ completeness ↔ rank
7. **University Comparative Analysis** — the leaderboards and the composite Academic Visibility Index
8. **Talent & Influence Analysis** — top researchers, bragworthy population, follower concentration
9. **Recommendations** — concrete next steps based on the findings (for whichever stakeholder the reader represents — platform vendor, university administrator, recruiter, research-intelligence buyer)
10. **Appendix: Data Quality Notes** — detailed caveats including coverage skew, zero-inflation in engagement fields, the rank=1 floor, and the snapshot nature of the data

Writing rules:
- Avoid implementation details, code explanations, or technical terminology
- Every claim must reference a specific chart
- Use exact numbers, not "many" or "significant"
- Embed all charts as images using markdown syntax: `![Title](charts/filename.png)`
- Group related charts together rather than listing them sequentially

## Scope and Constraints

- The analysis must remain strictly business-oriented
- Do not include algorithmic explanations, data preprocessing details, or model-level discussions
- Treat the README as a final business insight report, not technical documentation
- The final output should be suitable for direct inclusion in a business presentation or executive review
- All text in charts and README should be in English; keep original names only where they are part of the data being shown (researcher display names, university names, department names)
- `data.csv` is UTF-8 (no BOM) — read with `encoding='utf-8'`
- The CSV is small enough to load fully into pandas — no streaming required
- This is a static snapshot of the public registry — do not infer historical trends in engagement, growth rates, or year-over-year activity from numeric fields. The only time dimension you can analyze is `created_at` (account creation), and even that is upward-biased for the most recent years because newer researchers haven't yet had time to accumulate followers/papers.
- Do not analyze `photo_url` as anything other than a proxy for `has_photo` — the URL itself is a CDN artifact, not an analytical field
- Do not analyze `profile_url`, `department_url`, `scraped_at` as primary signals — they are operational metadata
- `user_id` is the primary key and is unique by construction; do not aggregate on it
- The `author_rank` field is almost-always 1.0 (platform floor) — when analyzing rank, restrict to the subset where rank ≠ 1 and note the subset size prominently
- The `bragworthy` field is a rare binary editorial signal (<1% True) — treat True rows as the platform-curated highlights
- Empty `followers_count` / `following_count` / `papers_count` correspond to a zero on the source profile; impute to 0 before any numeric analysis, and explicitly note this in the methodology section of the README
- Coverage skew is the single biggest risk in this dataset — always check per-subdomain counts in Step 0 and lead the README with a coverage disclosure if one university dominates
