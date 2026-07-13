# doyouneedahome-intelligence

Weekly SEO + website intelligence report for [doyouneedahome.com](https://www.doyouneedahome.com), for DO Homes Group at Premier Brokers International (John Oliver, Christine Dekant). Runs automatically every Monday morning via GitHub Actions and produces a concise, actionable report — not a generic SEO audit.

Modeled on the existing `condowpb-intelligence` daily-brief system, but scoped to this site's real content model (see "How city/community classification works" below) and automated end-to-end instead of running from a local Task Scheduler job.

This repo is standalone. It never touches the doyouneedahome.com website codebase — it only reads public data about it (Search Console, the sitemap, the live pages).

## What it produces

Every run writes three files to `reports/`:

```
reports/YYYY-MM-DD-doyouneedahome-intelligence.txt
reports/YYYY-MM-DD-doyouneedahome-intelligence.md
reports/YYYY-MM-DD-doyouneedahome-intelligence.json
```

covering: executive summary, page-1 opportunities, wins/losses, top pages/queries, quick wins, per-city authority scorecards (extra depth for Jupiter and Palm Beach Gardens), new content ideas, existing-content update ideas, internal-linking opportunities, lead-magnet placement, site health, new-development news watch, a money-keyword tracker, and a 5-item Monday action plan.

## Architecture

```
config/            site.yaml, cities.yaml, keywords.yaml, content_rules.yaml — all thresholds/lists live here, not in code
src/
  search_console.py    GSC auth + page/query data over 7d/prev7d/28d/prev28d
  sitemap.py            sitemap/sitemap-index parsing + diffing
  crawler.py             polite crawl + site-health aggregation
  rankings.py            opportunities / wins / losses / top pages / top queries / quick wins
  keyword_tracker.py     money-keyword tracker
  city_scorecards.py     per-city 0–100 scorecards (evidence-based, see below)
  content_ideas.py       new-content ideas, update-existing ideas, internal linking, lead magnets
  news_monitor.py        RSS-based new-development watch
  report_builder.py      assembles everything into TXT/MD/JSON
  storage.py              historical snapshots under data/historical/
  notifications.py       optional email delivery (SMTP / SendGrid / Resend)
  main.py                 orchestrator — every stage is isolated so one failed integration never kills the report
data/historical/    committed JSON snapshots (rank history, news dedupe ledger, sitemap baseline, one full snapshot per run)
reports/            committed weekly report output
tests/               pytest unit tests + tests/fixtures/sample_data.json for an offline dry run
.github/workflows/weekly-report.yml   the Monday automation
```

## How city/community classification works

The site's real URL structure (confirmed against the live sitemap) is flatter than a typical taxonomy: every city **and** every neighborhood/community lives under `/communities/{slug}` with no other distinguishing marker, and the site's relocation/lifestyle content is a repeatable per-city blog template (`/blog/what-its-really-like-living-in-{city}-florida`, etc.) rather than separate "luxury/waterfront/golf/55+" page types.

`config/cities.yaml` seeds a best-effort city → community mapping (`confidence: high` where I verified it, `confidence: seed` where it's a reasonable first guess). At runtime, `city_scorecards.classify_communities()`:

1. Matches sitemap URLs against the seeded mapping.
2. For anything unseeded, checks whether the crawled page's title/H1/body text mentions **exactly one** configured city by name — if so, auto-classifies it (`confidence: auto`).
3. Anything still ambiguous (zero or multiple city-name matches) is reported under **"Unmapped community pages"** in the report instead of being silently guessed.

Scorecard categories (community coverage, golf/waterfront/etc. tags) only count for a city when there's real evidence — a city with zero configured communities simply isn't scored on that axis rather than being penalized for a category that doesn't apply to it.

## Running locally

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env                # then fill in credentials
python -m src.main                  # live run — needs Search Console credentials
```

**Offline dry run (no credentials needed):**

```bash
python -m src.main --fixtures
```

This runs the full pipeline against `tests/fixtures/sample_data.json` (a small, realistic slice of doyouneedahome.com's actual URL structure) and writes real report files to `reports/`. Useful for verifying the pipeline or testing config changes without hitting live APIs.

**Tests:**

```bash
pytest -q
ruff check src/ tests/
```

## Credentials setup

### Google Search Console (required)

This system reuses the same Google Cloud service account already set up for `condowpb-intelligence` — no new GCP project needed. You only need to grant that service account access to the doyouneedahome.com property:

1. Open [Google Search Console](https://search.google.com/search-console) for `https://www.doyouneedahome.com` (or the domain property `sc-domain:doyouneedahome.com`).
2. **Settings → Users and permissions → Add user.**
3. Enter the service account's email address (the `client_email` field in the condowpb-intelligence `credentials.json`) and grant **Full** or **Restricted** access — Restricted (read-only) is sufficient, since this system only calls the read-only Search Console API.
4. Locally, either set `GSC_SERVICE_ACCOUNT_FILE` in `.env` to point at a copy of that same `credentials.json`, or set `GSC_SERVICE_ACCOUNT_JSON` to the full JSON contents as a single-line string.
5. Confirm `GSC_SITE_URL` in `.env` matches how the property is registered — defaults to `sc-domain:doyouneedahome.com`.

I did not touch or copy condowpb's actual credentials file as part of building this repo — this step is yours to do in the Google Search Console UI.

### GitHub Actions secrets

Set these under the repo's **Settings → Secrets and variables → Actions**:

| Secret | Required | Purpose |
|---|---|---|
| `GSC_SERVICE_ACCOUNT_JSON` | Yes | Full service-account JSON, single line |
| `GSC_SITE_URL` | No (defaults to `sc-domain:doyouneedahome.com`) | Override if the property is registered differently |
| `EMAIL_PROVIDER` | No | `smtp`, `sendgrid`, or `resend` — omit to skip email entirely |
| `REPORT_RECIPIENTS` | No | Comma-separated recipient list, required if `EMAIL_PROVIDER` is set |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | If using SMTP | e.g. Gmail app-password, same pattern as condowpb-intelligence |
| `SENDGRID_API_KEY`, `SENDGRID_FROM` | If using SendGrid | |
| `RESEND_API_KEY`, `RESEND_FROM` | If using Resend | |
| `GA4_PROPERTY_ID` | No | Reserved for a future GA4 adapter — unused today |
| `FUB_API_KEY` | No | Reserved for a future Follow Up Boss adapter — unused today |

Without `GSC_SERVICE_ACCOUNT_JSON`, the report still generates — the Search Console sections will show empty results and the run logs a clear "Search Console stage failed" error rather than crashing.

## Design trade-offs (as required by the report spec)

**Historical storage — committed JSON, not Actions artifacts.** GitHub Actions artifacts expire (90 days by default) and need extra API calls to read back in a later run. Small JSON files committed to `data/historical/` are durable, diffable in git history, and load with a single file read on the next run. The cost is a slowly growing repo — acceptable at roughly one snapshot a week of a few hundred KB. The weekly report files are *also* committed for the same durability reason, and additionally uploaded as a workflow artifact each run for convenience.

**Scheduling — a single Monday-11:00-UTC cron.** 11:00 UTC is 7:00 AM EDT / 6:00 AM EST. A fixed UTC cron drifts an hour across the DST boundary; rather than run two crons and add a same-day dedupe guard, this system accepts that the report fires at 6–7 AM Eastern depending on the time of year — always Monday morning, never off by a day. `workflow_dispatch` is available for exact-time manual runs.

## Triggering a report manually

- **From GitHub:** Actions tab → "Weekly Intelligence Report" → Run workflow.
- **Locally:** `python -m src.main` (or `--fixtures` for an offline test).

## How Monday automation works

`.github/workflows/weekly-report.yml` runs every Monday (see scheduling trade-off above): installs dependencies, lints (`ruff`) and tests (`pytest`) before generating anything, runs `python -m src.main`, uploads `reports/*` as a 90-day workflow artifact, and commits `reports/` + `data/historical/` back to the repository (skips the commit if nothing changed).

## Known limitations / integrations still needing your input

- **Search Console property access** — you need to add the service account as a user on the doyouneedahome.com GSC property (see above); nothing here can do that step for you.
- **Email delivery** — unconfigured by default. Set `EMAIL_PROVIDER` + the matching secrets to turn it on; until then, the report is available as a committed file and a workflow artifact every run.
- **GA4 / Follow Up Boss / lead-magnet download tracking** — not implemented. The report prints "Lead-source integration not configured." and "Market-data integration not configured." rather than fabricating numbers, per the report's own quality rules. These are placeholders for future adapters if you want to wire them up later.
- **`config/cities.yaml` community mappings marked `confidence: seed`** — a first-pass guess for communities I couldn't verify by hand (mostly the Lake Worth Beach and Port St. Lucie clusters). The auto-detection in `city_scorecards.py` will reclassify or flag these as more crawl data comes in; review and correct the YAML directly if you spot a wrong mapping.
- **MLS/listing data** — not scraped or fetched anywhere in this system, by design (spec rule: don't scrape MLS data without a legitimate configured source).
