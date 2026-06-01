# TASK.md

Build an MVP web page called **Real Estate Analytics: Lutsk**.

## Main goal

Create a small working project that can:

1. Collect listing statistics from predefined real estate URLs.
2. Save historical data into a local SQLite database.
3. Display charts on a web page.
4. Be easy to integrate later into my existing personal website.

## Data sources

Start with predefined URLs for real estate listings.

Preferred sources:

* OLX Ukraine
* DOM.RIA if easier or if API access is available

Important:
If direct OLX scraping is difficult or blocked, create the scraper structure anyway and use a mock/demo data mode first.

## Categories to support

Create a configuration file where I can add URLs for categories:

* Sale apartments, Lutsk
* Rent apartments, Lutsk
* Sale houses, Lutsk
* Sale commercial real estate, Lutsk
* 1-room apartments
* 2-room apartments
* 3-room apartments

Each category should have:

* category key
* category display name
* source name
* URL

## Database

Use SQLite.

Create a table for daily snapshots with fields:

* id
* date
* source
* category_key
* category_name
* url
* listings_count
* average_price
* average_price_per_m2
* created_at

For MVP, listings_count is the most important field.

If price or area cannot be parsed reliably, save NULL.

## Web page

Create a simple web page:

Title:
**Аналітика ринку нерухомості Луцька**

Show:

* total listing count chart over time;
* category selector;
* period selector: 7 days / 30 days / 90 days / all time;
* cards with current value, 7-day change, 30-day change;
* simple trend label: growing / falling / stable.

Use Chart.js for charts.

The visual style should be minimal and close to a personal portfolio website:

* light background;
* black text;
* rounded cards;
* simple buttons;
* responsive layout.

## Technical stack

Preferred:

* Python
* SQLite
* Flask or FastAPI
* HTML/CSS/JavaScript
* Chart.js

Suggested structure:

```text
real-estate-analytics/
  app.py
  scraper.py
  database.py
  config.py
  requirements.txt
  README.md
  data/
    real_estate.db
  templates/
    analytics.html
  static/
    analytics.css
    analytics.js
```

## Required commands

The project should support:

```bash
pip install -r requirements.txt
python database.py
python scraper.py
python app.py
```

Then the page should be available locally, for example:

```text
http://127.0.0.1:5000/analytics
```

## MVP priority

Do not overcomplicate.

First make one working chart with demo or real data.

Then extend to multiple categories.

The first result should be working, even if the scraper is not perfect.

## Important development instructions

* Write clean and simple code.
* Add comments where needed.
* Add README with setup instructions.
* Make the scraper modular so new sources can be added later.
* Do not hardcode everything directly in the scraper; use a config file for category URLs.
* If real parsing fails, create fallback demo data so the chart still works.
* Keep Ukrainian text on the visible web page.
