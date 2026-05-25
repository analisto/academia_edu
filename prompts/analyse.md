Analyze all CSV files in the `data/` directory with a strict focus on business value and decision-making insights, rather than technical or statistical explanations.

The data is scraped from the Azerbaijan Bar Association website (barassociation.az) and represents the public registry of licensed lawyers and the law firms ("Vəkil Büroları") they belong to.

## Datasets

| File | Records | Description | Key columns |
|------|---------|-------------|-------------|
| `firms.csv` | 145 | Law firm registry — every "Vəkil Bürosu" listed on barassociation.az/communities | community_id, name, head, address, phones, lawyers_url, cabinets_url, image_url, page, source_url |
| `lawyers.csv` | 2,599 | Licensed lawyer registry — every lawyer that appears under a firm via barassociation.az/lawyersearch | community_id, community_name, personal_id, name, address, phones, email, firm_label, languages, experience, education, specializations, image_url, source_url |

**Total: 2,744 structured records (across 2 datasets).**

The two datasets share a strict 1-to-many parent/child relationship through `community_id`: every lawyer in `lawyers.csv` belongs to exactly one firm in `firms.csv`. All 145 firms are represented in both datasets.

## Known Data Quality Issues (verified)

Flag these in the profiling step but do not let them block analysis:

| Issue | Impact | Handling |
|-------|--------|----------|
| `firms.image_url` — 98.6% empty | Most firms have no logo on the source site | Exclude from analysis |
| `firms.cabinets_url` — 66.2% empty | Only ~⅓ of firms expose a cabinets sub-listing on the source | Treat presence/absence as a binary signal, do not analyze the URL itself |
| `lawyers.specializations` — 57.5% empty | Practice-area field is optional on the source profile | Analyze available subset only (1,104 lawyers) |
| `lawyers.email` — 30.2% empty (the source explicitly shows "Elektron ünvanı daxil edilməyib" for these) | Optional field | Treat empty email as "no public email", do not impute |
| `lawyers.education` — 30.7% empty | Optional bio field | Analyze available subset only (1,800 lawyers) |
| `lawyers.phones` — 4.8% empty | Most lawyers do publish a phone | Analyze available subset; flag the 125 lawyers with no phone as a contactability gap |
| `lawyers.personal_id` — 0.2% empty (4 records) | The "VK" license number is the natural key but a handful are missing on the source | Note in the profile; fall back to (community_id, name) for deduplication |
| `lawyers.languages` includes a literal "Xarici dil biliyi yoxdur" ("no foreign language") for 1,097 lawyers | This is a populated value, not a blank | Treat as a separate category, do not count it as an actual language |
| Address strings are free-text Azerbaijani — no structured city/region field | Cannot join geographically without parsing | Derive a `region` field by string matching against a fixed list of Azerbaijani cities/rayons (Bakı, Gəncə, Sumqayıt, Mingəçevir, Naxçıvan, Şəki, Lənkəran, Qəbələ, Quba, etc.) |
| Experience field is a string like "12 il" / "0 il" | Needs parsing | Extract integer years with regex `(\d+)\s*il` and treat 0 as "less than one year" |
| Some lawyers' addresses contain phone numbers concatenated into the address text | Source-side data entry quality issue (~handful of records) | Note in the profile; do not over-engineer cleanup |
| The same head/director name can appear across multiple firms in `firms.head` | Possible (rare) — a single person may run more than one bureau | Check cardinality; do not assume one-to-one |

## Step 0: Data Profiling (mandatory before any analysis)

Before generating any charts or insights, run a full data quality audit on both CSVs:

- Row counts, column counts, file sizes
- Duplicate records — by `community_id` for firms, by `personal_id` and by `(community_id, name)` for lawyers
- Missing/empty values per column (count + percentage)
- Cardinality of categorical-style columns (`firm_label`, `community_name`, `languages`, `experience`)
- Distribution of `experience` (min, max, mean, median, p25/p75) after parsing years out of "X il"
- All CSVs use `utf-8-sig` encoding (BOM) — read with `encoding='utf-8-sig'`
- Cross-dataset consistency checks:
  - Every `lawyers.community_id` must exist in `firms.community_id` (referential integrity)
  - Every `firms.community_id` should appear in `lawyers.csv` at least once (no firms with zero lawyers); flag any that don't
  - `lawyers.community_name` should match `firms.name` for the same `community_id` (catch any drift)
  - `lawyers.firm_label` (free-text "Fəaliyyət göstərdiyi vəkil qurumu" from each lawyer's profile) should match the parent firm's `name` — measure mismatch rate

Print a summary table to the console. If critical issues are found (referential integrity breaks, >5% empty in `name`/`community_id`/`firm_label`, encoding issues), flag them before proceeding.

## Step 1: Charts Generation

Create a dedicated directory named `charts/`.

Implement a Python script named `scripts/generate_charts.py` that:

- Reads both datasets from `data/` and produces all required visualizations
- Uses only business-appropriate chart types (bar, horizontal bar, stacked bar, line, histogram, heatmap)
- Do NOT use pie charts under any circumstances
- Every chart must have a clear title, labeled axes, and readable fonts (min 10pt)
- Use a consistent color palette across all charts
- Save charts as PNG at 150+ DPI for presentation quality
- Handle Azerbaijani characters correctly (UTF-8 fonts — install/select a font that has the Azerbaijani Latin extended set: `ə`, `ı`, `ö`, `ü`, `ş`, `ç`, `ğ`, `İ`)
- Use `tight_layout()` or `constrained_layout=True` to prevent label clipping
- **After generating all charts, visually verify every single chart for readability.** Open each PNG and check:
  - Labels are not overlapping or cut off
  - Y-axis text is readable (no overlap when many bars)
  - Heatmap cells have legible numbers
  - Legend entries are not truncated beyond recognition
  - Stacked bars actually show meaningful segments
  - If any chart is unreadable, fix it before proceeding (reduce items, shorten labels, increase figure size)
- Firm names are long (e.g., "Bakı şəhəri 11 saylı Vəkil Bürosu") — shorten by stripping the "Vəkil Bürosu" suffix and truncating to ~35 chars on chart axes
- Region/city should be derived from the address with a fixed keyword list; show the residual "Other / unparsed" bucket explicitly so the audience knows what's missing

### Required chart categories (at minimum):

**Volume & Distribution:**
- Record counts across both datasets (overview bar: 145 firms, 2,599 lawyers)
- Lawyers per firm — top 20 firms by headcount (horizontal bar)
- Lawyers per firm — full distribution (histogram with bin width 5; show the median and mean lines)
- Firms with the smallest headcount — bottom 20 (boutique vs single-lawyer practices)
- Number of firms per page of the source listing (sanity check: 10 per page × 14 pages + 5 = 145)

**Geographic Distribution (derived from address text):**
- Lawyers by region — top 15 regions (Bakı, Gəncə, Sumqayıt, etc.) with an explicit "Other / unparsed" bar
- Firms by region — top 15 regions
- Lawyers per firm by region (which regions concentrate the largest firms vs the smallest?)
- Region × firm-size heatmap — rows: top 10 regions, columns: small/medium/large firm bands

**Lawyer Experience:**
- Experience-years histogram (bin width 5 years, 0–60)
- Experience by region — boxplot or grouped bar of mean years
- Experience by firm size — do bigger firms attract more senior lawyers?
- Top 20 firms by average lawyer experience (seniority leaderboard)
- Top 20 firms by share of lawyers with 20+ years of experience

**Languages:**
- Foreign-language coverage — bar chart of lawyers per language (Russian, English, Turkish, German, French, etc.) including a separate bar for "No foreign language" (1,097 lawyers)
- Multilingual depth — distribution of how many languages a lawyer speaks (0, 1, 2, 3+)
- Language coverage by region (heatmap: top 10 regions × top 6 languages)
- Language coverage by firm — top 20 firms by share of multilingual lawyers

**Specializations (1,104 lawyers, 42.5% of registry):**
- Top 20 practice areas (specializations) by number of lawyers
- Practice-area mix in the top 10 firms by headcount (stacked horizontal bar)
- Co-occurrence heatmap of the top 12 specializations (which areas tend to be combined?)
- Share of lawyers with at least one declared specialization, by region

**Education (1,800 lawyers, 69.3% of registry):**
- Top 15 universities/institutions named in the `education` field (after normalization — "Bakı Dövlət Universiteti" is by far dominant; show the share)
- Lawyers with vs without a populated education field, by firm size
- Education completeness by region

**Contactability:**
- Share of lawyers with at least one phone vs none (95.2% vs 4.8%)
- Share of lawyers with a public email vs none (69.8% vs 30.2%)
- Top 20 firms by email-publication rate (which firms encourage contactability?)
- Top 20 firms by phone-publication rate
- Email domain distribution — gmail vs mail.ru vs corporate (top 10 domains)

**Firm-level Comparative:**
- Headcount vs average experience scatter (top 30 firms labeled)
- Headcount vs language diversity scatter (top 30 firms labeled)
- Top 20 firms ranked by a composite "depth" score = headcount × average experience years
- Heads of firms (`firms.head`) cardinality — any individual running more than one firm?

**Network/Relationship (for future graph RAG context):**
- Lawyer-language bipartite heatmap — top 30 firms × top 6 languages
- Lawyer-specialization bipartite heatmap — top 30 firms × top 12 specializations
- Region-language heatmap (which regions have which language capacity?)
- Co-residence: lawyers from one firm whose address points to a different city than the firm's headquarters (mobility/branch indicator)

## Step 2: Insights and Findings

Identify key trends, patterns, anomalies, and relationships within the data that are relevant to business stakeholders (e.g., a legal-tech company building a lawyer-matching product, a bar association planning capacity, a corporate client choosing counsel, a law student planning a career).

Requirements:
- Every major insight MUST be directly supported by one or more charts
- Prioritize insights that can influence strategy, operations, market entry, talent acquisition, or risk reduction
- Include at minimum:
  - 2 firm-size insights (e.g., "the top 10 firms account for X% of all licensed lawyers in the country")
  - 2 geographic insights (e.g., "Bakı concentrates X% of all lawyers, the next region has only Y%")
  - 2 experience/seniority insights (e.g., "median lawyer experience is X years; firm A has the most senior bench at Y years")
  - 2 language/specialization insights (e.g., "X% of lawyers speak no foreign language; English-speaking lawyers are concentrated in N firms")
  - 1 contactability insight (e.g., "X% of lawyers do not publish a public email — flagged for the directory product")
  - 1 cross-dataset relationship insight (e.g., "the firms with the largest headcount are also the ones with the highest share of multilingual lawyers")
  - 1 anomaly or data quality insight worth noting (e.g., "the source's mandatory `firm_label` matches the parent firm name in X% of cases — Y mismatches indicate stale or migrated lawyer profiles")
- Quantify everything: use exact numbers, percentages, and comparisons — not vague statements
- Context matters: this is a snapshot of the public registry as of the scrape date, not a time series. Do not infer trends over time.

## Step 3: README Presentation Document

Document all findings in a `README.md` file at the project root.

The README must be written as a presentation-style narrative for non-technical stakeholders (e.g., executives, product owners, business managers, journalists, bar-association staff).

Structure:
1. **Executive Summary** — 5-7 bullet points with the most impactful findings
2. **Dataset Overview** — what data was scraped, scope, source URL, scrape date, record counts per dataset. Clarify that this is a public-registry snapshot, not historical activity data
3. **Data Quality Summary** — brief table showing completeness and any caveats per dataset (use the known issues table above)
4. **Key Findings** — organized by theme (Firm Size, Geography, Experience, Languages, Specializations, Contactability), each finding with:
   - What the chart shows (embed chart image)
   - Why it matters to the business
   - What decisions or actions it could inform
5. **Cross-Dataset Relationships** — dedicated section for insights that connect firms ↔ lawyers (e.g., the relationship between firm headcount and lawyer seniority, or between firm region and language coverage)
6. **Regional Analysis** — geographic distribution of legal capacity in Azerbaijan, derived from address parsing
7. **Talent & Capability Analysis** — what the experience, education, language, and specialization data reveal about the lawyer population
8. **Recommendations** — concrete next steps based on the findings (for whichever stakeholder the reader represents — directory operator, bar association, legal-tech vendor, or client)
9. **Appendix: Data Quality Notes** — detailed caveats stakeholders should know, including empty columns, the snapshot nature of the data, and the limitations of free-text address parsing

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
- All text in charts and README should be in English; keep original Azerbaijani names only where they are part of the data being shown (firm names, lawyer names, university names)
- Both CSVs are small (well under 1 MB combined) — load them fully into pandas, no streaming required
- This is a static snapshot of the public registry — do not infer historical trends, growth rates, or year-over-year change
- Do not analyze `firms.image_url` (98.6% empty), `firms.lawyers_url`/`firms.cabinets_url`/`firms.source_url` (these are scraping URLs, not analytical fields)
- Do not analyze `lawyers.image_url` or `lawyers.source_url` (scraping artifacts, not analytical)
- `community_id` is the join key between firms and lawyers — it is dense and reliable
- The `experience` field is a string ("12 il"); always parse to integer years before using it numerically
- The `languages` field is a comma-separated string; always split before counting; the literal "Xarici dil biliyi yoxdur" must be excluded from per-language counts and reported as a separate "no foreign language" segment
- Region is not a column in the source — derive it from `address` text via keyword matching against a fixed list of Azerbaijani cities/rayons, and always report an "Other / unparsed" bucket so the audience can see what fell outside the dictionary