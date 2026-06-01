# PROJECT_STATUS

Last updated: 2026-05-31

## MVP Direction

The MVP is now a simple Lutsk real-estate trend dashboard, not a full BI console.

The public `/analytics` page should answer one core question: how the number of listings is changing over time for sale and rent apartments in Lutsk. DOM.RIA and OLX must always remain separate sources.

## A. Current Architecture

- `app.py`
  Flask routes, public trend API, advanced analytics API, admin workflows, source separation.
- `database.py`
  SQLite schema, migrations, upsert logic, audit command, debug summary, manual-row diagnostics.
- `config.py`
  Category definitions, DOM.RIA params, display labels, database path.
- `scraper.py`
  Demo seeding, manual snapshot builder, live collection orchestration.
- `domria_scraper.py`
  DOM.RIA API integration, request logging, hourly protection, same-day skip logic.
- `templates/analytics.html`
  Simple public Ukrainian dashboard with two charts and five metric cards.
- `templates/analytics_advanced.html`
  Secondary technical page for filters/source diagnostics.
- `templates/admin.html`
  Ukrainian admin page for manual OLX entry, bulk snapshots, latest rows, suspicious/test rows.
- `static/dashboard.js`
  Public dashboard client logic for sale/rent trend charts.
- `static/analytics.js`
  Advanced filter client logic.
- `static/analytics.css`
  Shared minimal styling.
- `README.md`
  Setup, local usage, scraper, admin, and deployment notes.
- `data/real_estate.db`
  Local SQLite store. Do not commit or delete without explicit intent.

## Data Flow

1. DOM.RIA live collection writes real rows with `source='DOM.RIA'` and `data_source='domria'`.
2. Manual/admin OLX entry writes manual rows with `source='OLX'` and `data_source='manual'`.
3. Demo seeding writes fallback rows with `data_source='demo'`.
4. SQLite upsert identity is:
   `date + source + data_source + deal_type + property_type + rooms + location_scope`.
5. Public `/api/analytics/trends` reads only:
   DOM.RIA real rows and OLX manual rows for apartments/all rooms/Lutsk.
6. Public `/analytics` renders two charts:
   sale trend and rent trend, each with separate DOM.RIA and OLX lines.
7. `/analytics/advanced` and `/api/analytics` remain available for technical checking.

## B. Existing Functionality

### Public Analytics

- Route: `/analytics`
- Ukrainian-only visible UI.
- Two charts only:
  sale apartments all rooms, rent apartments all rooms.
- Each chart has separate lines:
  DOM.RIA and OLX.
- Demo data is excluded from the public charts.
- Cards show:
  latest DOM.RIA sale count, latest OLX sale count, latest DOM.RIA rent count, latest OLX rent count, last update date.

### Advanced Analytics

- Route: `/analytics/advanced`
- Keeps the filter-heavy view out of the public default page.
- Supports source filter, deal type, property type, rooms, location, period.
- Selected source remains stable when other filters change.
- `All sources` remains separate lines instead of a merged fake total.

### Admin

- Route: `/admin`
- Ukrainian secondary admin UI.
- Single manual OLX row entry.
- Bulk OLX daily snapshot entry.
- Bulk upsert updates matching rows instead of duplicating them.
- Latest manual snapshot groups table.
- Latest 50 manual rows table with manual-row delete buttons.
- Suspicious/test manual row section. It marks rows for review only; no automatic deletion.

### DOM.RIA Scraper

- Live collection is available through `python scraper.py --live`.
- Request logging exists in `domria_request_log`.
- Hourly protection exists in code.
- Same-day already-collected real categories are skipped.
- This audit did not call the DOM.RIA API.

### Audit/Debug

- `python database.py --audit`
  prints totals by date, source, source name, location, latest DOM.RIA/manual rows, and dates per active category.
- `/api/analytics/debug`
  returns JSON summary of available sources, dates, row counts, manual row count, and DOM.RIA row count.

## C. Current Categories Tracked

### Main Public MVP Categories

- `sale_apartments_all`
- `rent_apartments_all`

### Active DOM.RIA Categories

- `sale_apartments_all`
- `sale_apartments_1`
- `sale_apartments_2`
- `sale_apartments_3`
- `rent_apartments_all`
- `rent_apartments_1`
- `rent_apartments_2`
- `rent_apartments_3`
- `sale_houses_all`
- `sale_commercial_all`

### Manual OLX Bulk Categories

- Sale apartments: all, 1, 2, 3, 4+
- Rent apartments: all, 1, 2, 3, 4+
- Sale houses all
- Sale commercial all
- Sale land all

## D. Current Data Sources

- DOM.RIA real:
  `source='DOM.RIA'`, `data_source='domria'`
- OLX manual:
  `source='OLX'`, `data_source='manual'`
- Demo:
  `data_source='demo'`; allowed for development/advanced mode only, excluded from public MVP charts.

## Current Data Audit

### DOM.RIA Real Rows

- Dates found: `2026-05-31`
- Row count: `10`
- Real counts by category on `2026-05-31`:
  `sale_apartments_all=435`,
  `sale_apartments_1=171`,
  `sale_apartments_2=155`,
  `sale_apartments_3=84`,
  `rent_apartments_all=186`,
  `rent_apartments_1=113`,
  `rent_apartments_2=49`,
  `rent_apartments_3=22`,
  `sale_houses_all=43`,
  `sale_commercial_all=0`.
- No earlier real DOM.RIA date was found in the current SQLite database.

### OLX Manual Rows

- Dates found: `2026-05-29`, `2026-05-30`, `2026-05-31`
- Total OLX manual row count: `29`
- `2026-05-29`: 13 rows, created on `2026-05-31 20:10:40`.
  These look like Codex test bulk snapshot rows and are flagged in `/admin`.
- `2026-05-30`: 3 rows.
  These look like earlier/manual sample rows.
- `2026-05-31`: 13 rows, created on `2026-05-31 20:27:36`.
  These look like a full manual/admin OLX snapshot.

## E. Request Budget Analysis

- Active live DOM.RIA categories: `10`
- Expected daily requests for one full collection: about `10`
- Estimated monthly usage: about `300` requests/month.
- Free DOM.RIA plan previously documented as `1,000` requests/month and `30` requests/hour.
- Current code safety limit: `25` requests/hour.
- Estimated monthly safety margin: about `700` requests.

## F. Known Issues

- Real DOM.RIA history is shallow: only `2026-05-31` exists as real data.
- OLX manual history contains a likely Codex test snapshot for `2026-05-29`.
- Demo rows are still present in the database and advanced mode; they are intentionally excluded from the public MVP charts.
- `/admin` and debug endpoints are not authenticated.
- The app has no automated test suite.
- Chart.js loads from CDN; offline/local vendoring may be better before deployment.
- SQLite deployment on Railway needs a persistence and backup decision.
- Railway volumes are service-specific. Do not use a separate Railway scheduler service with SQLite because it can write to a different `/data/real_estate.db` than the web service reads. Use the protected `/admin` collection action until persistence moves to Postgres or another shared database.
- Ukrainian text in some config-derived labels may need a final encoding/copy review before public deployment.

## G. Recommended Roadmap

### Priority 1: Required Before Deployment

- Add access control for `/admin`, delete actions, and debug endpoints.
- Decide production database handling:
  Railway volume, backup/export script, or migration path.
- Confirm whether the likely Codex test OLX rows from `2026-05-29` should be deleted manually.
- Collect at least a few more real DOM.RIA daily snapshots so the trend chart is meaningful.
- Add smoke tests for `/analytics`, `/api/analytics/trends`, `/admin`, and manual upsert behavior.
- Confirm no real API key is tracked before GitHub push.

### Priority 2: Important Improvements

- Add scheduled daily DOM.RIA collection after moving from service-local SQLite volume storage to Postgres or another shared database.
- Add a simple database backup command.
- Vendor Chart.js locally or document the CDN dependency.
- Clean up old demo/demo-source rows when the MVP no longer needs them, with explicit backup first.
- Polish Ukrainian labels from `config.py` if any encoding artifacts appear in rendered UI.

### Priority 3: Future Ideas

- Add price and price-per-square-meter trends.
- Add optional house/commercial charts after sale/rent apartments stabilize.
- Add CSV export for snapshots.
- Move from SQLite to Postgres if production usage grows.

## H. Deployment Checklist

### GitHub

- Confirm `.gitignore` excludes `domria_config.json`.
- Confirm `.gitignore` excludes SQLite database files.
- Scan tracked files for real API keys before committing.
- Commit code only; do not commit local database or real config.

### Railway

- Set environment variables for DOM.RIA API access.
- Decide database persistence before enabling live collection.
- Add a backup/export plan.
- Do not expose `/admin` publicly without authentication.

### Runtime

- Install dependencies from `requirements.txt`.
- Run database initialization before first request.
- Verify `/analytics` loads the simple dashboard.
- Verify `/api/analytics/trends` excludes demo data.
- Verify `/admin` loads and manual delete only affects manual rows.

## Latest Verification

- `/analytics` returned HTTP 200.
- `/admin` returned HTTP 200.
- `/analytics/advanced` returned HTTP 200.
- `/api/analytics/trends` returned only DOM.RIA and OLX datasets.
- Browser check found exactly two public chart canvases:
  `saleTrendChart`, `rentTrendChart`.
- Browser check found no visible demo text on the public dashboard.
- Browser check found no old English labels on the public dashboard.
- Browser check confirmed `/admin` has a link back to `/analytics`.
- Browser check confirmed `/admin` shows 13 suspicious/test manual rows.
- Python syntax compilation passed for `app.py`, `database.py`, `scraper.py`, and `domria_scraper.py`.
- No DOM.RIA API call, deployment, GitHub push, or database deletion was performed during this audit.
