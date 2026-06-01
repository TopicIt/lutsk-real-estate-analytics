# Deployment Checklist

## GitHub

- [ ] Confirm `domria_config.json`, SQLite databases, logs, virtualenvs, and `__pycache__` are ignored.
- [ ] Create the GitHub repository.
- [ ] Push the code to GitHub.
- [ ] Confirm no real API key is visible in the repository.

## Railway Web Service

- [ ] Create a Railway project from the GitHub repository.
- [ ] Use the web start command from `Procfile`: `gunicorn app:app --bind 0.0.0.0:$PORT`.
- [ ] Add environment variables:
  - `FLASK_ENV=production`
  - `DOMRIA_API_KEY=<Railway secret>`
  - `ADMIN_PASSWORD=<strong password>`
  - `DATABASE_PATH=/data/real_estate.db`
- [ ] Configure a Railway volume mounted at `/data`.
- [ ] Deploy the web service.
- [ ] Open `/analytics` and confirm the public charts load.
- [ ] Open `/admin` and confirm it asks for the admin password.
- [ ] Confirm `/api/analytics/debug` is not available in production.

## Railway Cron

- [ ] Create a Railway cron job using `python scheduler.py --run-once`.
- [ ] Use the same `DOMRIA_API_KEY` and `DATABASE_PATH=/data/real_estate.db` variables.
- [ ] Test scheduler planning first with `python scheduler.py --dry-run`.
- [ ] Run live collection only once after confirming the plan.
- [ ] Re-check `/analytics` after the first live collection.
