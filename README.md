# Real Estate Analytics: Lutsk

Small Flask MVP for tracking the Lutsk real estate market with SQLite storage, Chart.js charts, demo fallback data, and live DOM.RIA scraping.

## Stack

- Python
- Flask
- SQLite
- Chart.js

## Local Run

Install dependencies:

```bash
pip install -r requirements.txt
```

Initialize the database:

```bash
python database.py
```

Run demo data collection:

```bash
python scraper.py
```

Start the app:

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000/analytics
```

Manual data admin:

```text
http://127.0.0.1:5000/admin
```

The Flask entrypoint is also safe for hosting platforms. It binds to `0.0.0.0` and uses the `PORT` environment variable when present.

Local `/admin` access is open by default. In production, set `FLASK_ENV=production` and `ADMIN_PASSWORD` to require HTTP Basic auth for `/admin`.

## DOM.RIA Config

Live DOM.RIA scraping is configured through a local file that is not committed:

```text
domria_config.json
```

Create it from the example file:

```bash
copy domria_config.example.json domria_config.json
```

Never commit real DOM.RIA API keys. Keep `domria_config.json` local, and use environment variables such as `DOMRIA_API_KEY` for hosted environments.

Example structure:

```json
{
  "api_key": "PUT_YOUR_DOMRIA_API_KEY_HERE",
  "state_id": 18,
  "city_id": 18
}
```

Current defaults:

- `state_id=18` for Volyn region
- `city_id=18` for Lutsk

You can also override per-category DOM.RIA parameters inside the `categories` object in `domria_config.json`.

Check configuration safely without printing the real key:

```bash
python domria_scraper.py --check-config
```

## OLX Integration

OLX integration is experimental and not part of automatic daily collection yet.
Current OLX data can still be entered through the manual `/admin` workflow.

The OLX proof of concept reads only two configured search URLs:

- `OLX_SALE_APARTMENTS_URL`
- `OLX_RENT_APARTMENTS_URL`

Set them locally or as Railway variables. They should point to the OLX.ua search
pages for sale apartments in Lutsk and rent apartments in Lutsk, all rooms.
In Railway, add them under the web service Variables tab, for example:

```text
OLX_SALE_APARTMENTS_URL=https://www.olx.ua/uk/nedvizhimost/kvartiry/prodazha-kvartir/lutsk/
OLX_RENT_APARTMENTS_URL=https://www.olx.ua/uk/nedvizhimost/kvartiry/dolgosrochnaya-arenda-kvartir/lutsk/
```

Run a local test without writing to SQLite:

```bash
python olx_scraper.py --test
```

If both counts parse successfully, save them as existing OLX/manual rows:

```bash
python olx_scraper.py --save-manual
```

The admin page also has a protected `Запустити збір OLX зараз` button that saves
only the two MVP OLX counts as OLX/manual rows. A future external cron can call
`POST /api/collection/run-olx` with the same bearer token style as DOM.RIA:

```bash
curl -X POST https://YOUR_DOMAIN/api/collection/run-olx \
  -H "Authorization: Bearer YOUR_COLLECTION_TOKEN"
```

This is intentionally separate from the DOM.RIA scheduler and from Railway cron.
It may stop working if OLX blocks the request or changes the search page HTML.
When parsing fails, the command prints a clear message and skips saving bad data.

## Live Scraping

Run demo mode:

```bash
python scraper.py
```

Add a manual market data row without calling any external API:

```bash
python scraper.py --manual
```

You can also pass the fields directly:

```bash
python scraper.py --manual --date 2026-05-30 --source-name OLX --deal-type sale --property-type apartments --rooms 1 --location-scope lutsk --listings-count 100
```

Rebuild demo history and align it to the latest real DOM.RIA rows already stored in SQLite:

```bash
python scraper.py --seed-demo --align-to-real
```

Run live DOM.RIA mode with demo fallback:

```bash
python scraper.py --live
```

Manual safe usage:

```bash
python scraper.py --live --max-requests 5
```

Run one autonomous daily collection pass:

```bash
python scheduler.py --run-once
```

Preview the next autonomous pass without calling DOM.RIA:

```bash
python scheduler.py --dry-run
```

Force a fresh live request even if today's real DOM.RIA data already exists:

```bash
python scraper.py --live --force
```

There is also a direct DOM.RIA collector:

```bash
python domria_scraper.py
```

## Manual Market Data

Use the admin page for browser-based manual entry:

```text
http://127.0.0.1:5000/admin
```

Fill in source name, deal type, property type, rooms, location scope, listings count, and date, then save the entry. Listings count must be a positive whole number, and date is required. The table below the form shows the latest 50 manual rows and includes a delete button for manual entries.

For a full daily OLX snapshot, use the bulk OLX snapshot form on `/admin`. Set the common date and location scope, fill only the categories you checked, and leave unknown fields empty. Saving the same date/source/location/category again updates the existing manual row instead of creating duplicates.

Manual rows are stored with:

- `data_source = manual`
- a custom `source` name such as `OLX`
- `location_scope = lutsk` or `lutsk_suburbs`

This makes it possible to keep:

- DOM.RIA real API data
- manually entered market checks
- demo fallback history

all in the same analytics page without overwriting each other.

Example manual data:

- Sale apartments, 1 room, Lutsk = `100` listings
- Sale houses, Lutsk + suburbs = `174` listings
- Sale land plots, Lutsk + suburbs = `47` listings

Example commands:

```bash
python scraper.py --manual --source-name OLX --deal-type sale --property-type apartments --rooms 1 --location-scope lutsk --listings-count 100
python scraper.py --manual --source-name OLX --deal-type sale --property-type houses --rooms all --location-scope lutsk_suburbs --listings-count 174
python scraper.py --manual --source-name OLX --deal-type sale --property-type land --rooms all --location-scope lutsk_suburbs --listings-count 47
```

## Daily Request Limits

The project is tuned for request economy.

- Live DOM.RIA scraping runs at most once per day per category when real data already exists.
- If today's real DOM.RIA row is already in SQLite for the same category, the scraper skips the API call.
- Every DOM.RIA request attempt is logged in SQLite in `domria_request_log`.
- Before any new DOM.RIA call, the scraper checks requests made in the last 60 minutes.
- A safety limit of `25` requests per hour is used instead of the full plan limit of `30`.
- If the hourly safety limit is reached, the scraper stops safely and leaves the remaining categories for a later run.
- `--max-requests` lets one run collect only a small batch of missing categories.
- Demo fallback is used if the API is unavailable, rate-limited, or a category request fails.
- `--force` bypasses the same-day cache and should be used carefully.
- `--seed-demo --align-to-real` refreshes only demo history and keeps any real DOM.RIA rows untouched.

Current active DOM.RIA categories:

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

Disabled by default to protect request budget:

- `sale_apartments_4_plus`
- `rent_apartments_4_plus`

Expected monthly usage with the current active set:

```text
10 categories x 30 days = about 300 requests/month
```

Recommended gradual collection:

- Run `python scraper.py --live --max-requests 5`
- Repeat every 2-3 hours
- This lets the project fill missing categories during the day without pushing close to the hourly ceiling

## Daily Scheduler

The project includes a small scheduler entrypoint:

```bash
python scheduler.py --run-once
```

It runs one safe DOM.RIA collection pass with the same behavior as:

```bash
python scraper.py --live --max-requests 10
```

Before making requests, it respects the existing protections:

- skips DOM.RIA categories already collected today
- checks the hourly safety limit
- stops safely when the API returns `429 HourOverlimit`
- logs the run summary in SQLite

To check what would happen without making any API request:

```bash
python scheduler.py --dry-run
```

The public app exposes scheduler status at:

```text
/api/collection/status
```

### Windows Task Scheduler

Recommended local schedule: once per day at `09:00`.

Create a basic scheduled task:

1. Open Windows Task Scheduler.
2. Choose `Create Basic Task`.
3. Name it `Lutsk DOM.RIA Daily Collection`.
4. Trigger: `Daily`, time `09:00`.
5. Action: `Start a program`.
6. Program/script: path to your Python executable.
7. Arguments:

```text
scheduler.py --run-once
```

8. Start in:

```text
D:\lutsk-real-estate-analytics
```

If Python is not on PATH, use the full Python path in `Program/script`.

### Railway Scheduling Notes

Do not store `domria_config.json` in GitHub or Railway. Use Railway environment variables such as `DOMRIA_API_KEY`.

For the SQLite MVP on Railway, do not use a separate Railway scheduler service. Railway volumes are service-specific, so a scheduler service can write to a different `/data/real_estate.db` than the web service reads.

Run DOM.RIA collection from the protected web admin page instead:

```text
/admin
```

Use the `Запустити збір DOM.RIA зараз` button so collection writes into the same web-service SQLite volume used by `/analytics`. A separate scheduler service should wait until the database is moved to Postgres or another shared database.

## Railway Deployment

The MVP is ready for a small Railway deployment without adding new analytics features.

Public page:

```text
/analytics
```

Web process:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

This is already captured in `Procfile`.

Required Railway environment variables:

```text
FLASK_ENV=production
DOMRIA_API_KEY=<your Railway secret>
ADMIN_PASSWORD=<strong admin password>
COLLECTION_TOKEN=<strong collection trigger token>
DATABASE_PATH=/data/real_estate.db
```

Optional DOM.RIA location overrides:

```text
DOMRIA_STATE_ID=18
DOMRIA_CITY_ID=18
```

SQLite remains the MVP database. For Railway persistence, create a Railway volume mounted at:

```text
/data
```

Then set:

```text
DATABASE_PATH=/data/real_estate.db
```

Do not commit `domria_config.json`; it is for local development only and is ignored by git. Railway should use `DOMRIA_API_KEY`.

### Railway Cron

Do not configure a separate Railway cron service while the MVP uses SQLite on a Railway volume. Railway volumes are attached per service, so cron and web services can end up with different databases at the same `/data/real_estate.db` path.

Use the protected `/admin` collection button or an external cron request to the web service for now. Revisit Railway cron after moving persistence to Postgres or another shared database.

### External Cron

External cron services can trigger collection inside the web service, which writes to the same SQLite database used by `/analytics`.

Set this Railway variable on the web service:

```text
COLLECTION_TOKEN=<strong collection trigger token>
```

Trigger URL:

```text
POST https://YOUR_DOMAIN/api/collection/run
```

Authorization header:

```text
Authorization: Bearer YOUR_COLLECTION_TOKEN
```

Example curl:

```bash
curl -X POST https://YOUR_DOMAIN/api/collection/run \
  -H "Authorization: Bearer YOUR_COLLECTION_TOKEN"
```

Good MVP options:

- `cron-job.org`: schedule a daily HTTP POST to `/api/collection/run` with the bearer token header.
- `EasyCron`: schedule a daily HTTP POST to `/api/collection/run` with the bearer token header.
- GitHub Actions scheduled workflow: future option if you want the schedule stored in GitHub, but keep the request as an HTTP POST to the web service while SQLite remains on the web volume.

Check the latest run:

```text
GET /api/collection/status
```

## Data Notes

SQLite database path:

```text
data/real_estate.db
```

Main table:

```text
daily_snapshots
```

The analytics API supports structured filters such as:

```text
/api/analytics?deal_type=sale&property_type=apartments&rooms=all&period=30
/api/analytics?deal_type=rent&property_type=apartments&rooms=2&period=7
/api/analytics?deal_type=sale&property_type=houses&rooms=all&period=30
```
