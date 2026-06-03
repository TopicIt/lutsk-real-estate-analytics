# OLX Integration Plan

Prepared on 2026-06-03. This plan is intentionally limited to research and
preparation. No OLX collection is active, no DOM.RIA logic is changed, and no
database data should be modified by this phase.

## Current Project Findings

DOM.RIA automatic collection is isolated in `domria_scraper.py` and
`scheduler.py`. The web process calls `scheduler.run_once()` from
`app.run_collection_in_web_process()`, and the protected `/api/collection/run`
route only triggers DOM.RIA collection after bearer-token validation.

DOM.RIA rows are written to `daily_snapshots` with `source = 'DOM.RIA'` and
`data_source = 'domria'`. The collector skips same-day real rows per category,
logs DOM.RIA requests in `domria_request_log`, and has an hourly safety limit.

Manual OLX rows are stored through `/admin` and `scraper.py --manual`.
They are written to the same `daily_snapshots` table with `source = 'OLX'`,
`data_source = 'manual'`, category fields, location scope, count, and date.
The uniqueness key updates the same date/source/category instead of duplicating
manual snapshots.

Public `/analytics` reads only apartment/all-rooms/Lutsk trends. In
`build_public_trend()`, DOM.RIA data comes from `fetch_snapshots(...,
source_filter='domria')`; OLX data comes from `fetch_snapshots(...,
source_filter='olx')`. The OLX filter currently means `data_source = 'manual'`
and `lower(source) = 'olx'`, so automatic OLX rows should not be introduced
under a new data source until the analytics contract is reviewed.

## A. Official OLX API Option

Official OLX Ukraine developer documentation exists at:

- https://developer.olx.ua/api/doc
- https://developer.olx.ua/ua/articles/getting-access-to-api
- https://developer.olxgroup.com/products

The official Partner API is designed for authenticated partners to publish,
manage, promote, and inspect their own adverts and messages. The available
`GET /api/partner/adverts` endpoint is "Get user adverts" and requires an
access token. It supports filters like `offset`, `limit`, `external_id`, and
`category_ids`, but it is scoped to the authenticated user's adverts rather than
public marketplace search results.

The OLX Group product page describes OLX Partner APIs as inventory-management
integrations for partners and notes the OLX Europe API is stable, with no new
development or maintenance. The Ukraine access flow also requires logging in,
adding an app, and waiting for approval before receiving Client ID and Client
Secret credentials.

Assessment: the official Partner API is unlikely to provide public listing
counts for "sale apartments in Lutsk" or "rent apartments in Lutsk" unless OLX
grants a separate search/data product that is not visible in the public Partner
API documentation. It is still worth contacting OLX support with this exact
question before choosing scraping.

## B. Direct Page Count Scraping Option

This option would request the public OLX search pages configured by:

- `OLX_SALE_APARTMENTS_URL`
- `OLX_RENT_APARTMENTS_URL`

The collector would parse only the visible total listing count for the two MVP
categories:

- `sale_apartments_all`
- `rent_apartments_all`

Implementation should stay separate from DOM.RIA, run behind an explicit
feature flag, and avoid writing database rows until count parsing is verified.
Once approved, it can convert counts into the same snapshot shape currently
used by manual OLX rows.

Assessment: this is the lowest-code MVP path, but it has the highest blocking
and Terms of Service risk. It should start with a dry-run command and HTML
fixture tests before any live request is enabled.

## C. Apify / Third-Party Scraper Option

Apify has multiple OLX/OLX.ua scraper actors, including actors that advertise
support for OLX Ukraine and public listing extraction:

- https://apify.com/automation-lab/olx-ukraine-classifieds-scraper
- https://apify.com/daddyapi/olx-search-scraper
- https://apify.com/abotapi/olx-scraper

This option delegates anti-blocking, browser/proxy behavior, and parser
maintenance to a paid third-party service. The app would call Apify, collect
only counts or minimal listing metadata, and write snapshots after validation.

Assessment: this may be more reliable than direct scraping, but it adds cost,
vendor dependency, API-token handling, and still may carry ToS/legal questions.

## D. Manual Fallback Option

Keep the current `/admin` bulk OLX snapshot form as the production fallback.
It already writes rows with the schema and source filters that `/analytics`
expects. This is the safest option while DOM.RIA is working and OLX automatic
collection is being validated.

Assessment: manual fallback has no external API risk and no new deployment risk,
but it depends on consistent human entry and does not scale.

## E. Risks

API access limitations: OLX Partner API access requires approval, OAuth
credentials, and authenticated user scope. Public search counts do not appear to
be available in the documented Partner API.

Scraping blocking: public OLX pages may use dynamic rendering, bot detection,
rate limiting, markup changes, or regional behavior that breaks a simple parser.

Legal/ToS risk: direct scraping or third-party scraping should be reviewed
against OLX terms and the intended data use. API terms also allow OLX to reject
apps, block keys, or limit API access.

Maintenance risk: page-count parsing is fragile. Third-party actors reduce local
maintenance but introduce vendor and version drift.

Cost: official API may require partner approval and business constraints.
Direct scraping is cheap but fragile. Apify/third-party services add recurring
usage and proxy costs.

## F. Recommended MVP Path

1. Keep DOM.RIA unchanged and leave `/analytics` source behavior unchanged.
2. Keep manual OLX bulk entry as the only active OLX production path.
3. Contact OLX support/partner API with a precise question: can an approved app
   read public search result counts for OLX.ua real estate by city/category?
4. Add only inert placeholders now: `OLX_SALE_APARTMENTS_URL`,
   `OLX_RENT_APARTMENTS_URL`, and a non-wired `olx_scraper.py` stub.
5. If OLX confirms no official public count endpoint, prototype direct page
   count parsing locally with saved fixtures first, then a feature-flagged
   dry-run command that makes at most two requests.
6. If direct parsing is blocked or unstable, evaluate Apify with a capped trial
   and compare cost/reliability against weekly manual entry.
7. Only after validation, add a separate OLX collection command that writes
   counts in a way compatible with the existing OLX analytics filters.
