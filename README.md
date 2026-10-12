# Fishing AI

**Work in Progress – Actively Developed**

Fishing AI is a personal fishing journal and planning application for Finnish lake fishing. It combines private trip and catch records, weather forecasts, interactive maps, and an AI-powered assistant. The application has a Finnish-language interface, responsive layouts, and light and dark themes.

This is an actively developed portfolio project. The current features are implemented and covered by automated tests; the application is not presented as a finished commercial product or a scientifically validated fishing prediction service.

## Current features

- **Fishing trips and catches:** create, edit, and delete trips; record conditions and multiple catches in one submission; distinguish explicitly empty trips from missing catch information.
- **AI-powered fishing assistant:** ask about your own history or upcoming fishing conditions. The server resolves dates and places, compares forecast times, and computes a deterministic 1–10 conditions score. OpenAI provides a written explanation; limited personal history affects confidence rather than reducing the conditions score.
- **Weather forecasts:** FMI observations and forecasts, editable trip weather fields, a default weather location, and a compact homepage forecast. Missing weather is reported rather than invented.
- **Fishing spots and maps:** private saved locations on Leaflet/OpenStreetMap maps, optional trip links, draggable markers, and browser geolocation requested only after a button press.
- **Catch statistics and records:** species, lure, time-of-day and location summaries; personal weight and length records; the current month's three heaviest catches.
- **User authentication:** Django authentication, registration, profile editing, password changes, and password-confirmed account deletion. Application queries restrict personal records to their owner.
- **Catch photos:** optional validated JPEG, PNG and WebP uploads, normalized to JPEG with metadata removed. Photos are served through an authenticated owner-checked endpoint rather than public media URLs.

## Technology

| Area | Technologies |
| --- | --- |
| Backend | Python, Django, Django authentication and ORM |
| Database | PostgreSQL in production; SQLite for local development |
| Frontend | Django templates, JavaScript, Bootstrap, CSS |
| AI | OpenAI Responses API, bounded requests and server-side scoring |
| Weather | Finnish Meteorological Institute (FMI) open data |
| Maps | Leaflet and OpenStreetMap |
| Public place lookup | FMI, with a cached and rate-limited Nominatim fallback |
| Deployment | Railway, Gunicorn, WhiteNoise |
| Validation and tests | Django test runner, Node.js test runner, JSON Schema |

The browser submits requests to Django. The backend handles ownership checks, weather retrieval, place/date interpretation and scoring before making an optional OpenAI request. No OpenAI request is triggered merely by opening the assistant page.

## Local development

Use a Python version compatible with the pinned Django release in `requirements.txt`. Node.js is needed to run the JavaScript tests. Run commands from the repository root.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

On macOS/Linux, activate with `source .venv/bin/activate`. Open `http://127.0.0.1:8000/` and register a local account. An optional administration account can be created with `python manage.py createsuperuser`.

Without `DATABASE_URL`, local development uses an ignored SQLite database. In development, Django generates an ignored local `.django-secret-key` file when no environment key is provided. Do not reuse that key in production.

`.env.example` documents configuration; the application does **not** automatically load `.env` files. Use process environment variables. Do not place credentials in source files or shell commands saved to history.

### Optional AI configuration

The journal works without an OpenAI key. To enable the assistant locally in PowerShell, enter a key without putting its value into command history:

```powershell
$assistantSecret = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $assistantSecret).Password
python manage.py runserver
```

Set the variable in the same terminal that starts Django. API usage may incur charges. `OPENAI_MODEL` optionally overrides the configured default model.

The assistant permits at most 10 dispatched OpenAI requests per user per rolling hour, one call per submission, a 30-second request timeout, no automatic retries, and a bounded response token budget. Weather and map features require access to their external providers.

## Tests and checks

```powershell
python manage.py test --noinput
node --test fishinglog/js_tests/*.test.cjs
python manage.py check
python manage.py check_fishing_knowledge
```

Tests cover ownership boundaries, CRUD operations, private photos, assistant privacy and usage limits, weather failure handling, place/date interpretation, scoring, forms and browser interactions. External API responses are mocked in the test suite; real OpenAI calls are not required. Tests use a separate test database and temporary photo storage.

Static assets can be prepared with `python manage.py collectstatic --noinput`. Generated assets are ignored by Git.

## Privacy and data handling

Trips, catches, saved fishing spots, photos and statistics are scoped to the signed-in user. Precise locations are not shown in record or monthly top-three cards. Photo access is checked on every request; a difficult-to-guess filename is not treated as authorization.

When a user submits an assistant question, OpenAI receives the question, place names, bounded structured trip/catch history, weather values and server-calculated assessments. Stored precise coordinates and free-form notes are removed from the outbound payload by default, including coordinate fields and location-bearing weather source text. Exact coordinates remain available to the backend for weather retrieval and daylight estimation; necessary location information is sent to FMI for weather requests.

A separate, optional checkbox permits notes from **one selected owned fishing spot** for that submission: at most 250 characters per field and 2,000 characters in total from the bounded history sample. This permission is not stored in the session. Coordinate-like pairs are also filtered from text, but this is not a general personal-data anonymizer: do not enter secrets or sensitive personal information in questions or notes shared with the assistant.

The OpenAI request uses `store=false`; answers are not saved to the application's database. This does not assert that an external provider has no retention of its own. Public geocoding sends only the public place/area needed for resolution, not the complete question or private saved-spot data. OpenStreetMap tiles are requested by the browser. No real user data or private-location screenshots are included in this README.

## Deployment configuration

The repository includes Railway configuration for `collectstatic`, a pre-deploy migration step, and Gunicorn startup. Production requires:

- `DJANGO_ENV=production` and `DEBUG=False`.
- A strong, independently generated `DJANGO_SECRET_KEY`.
- A PostgreSQL `DATABASE_URL` supplied through the hosting environment.
- Exact `ALLOWED_HOSTS` and HTTPS `CSRF_TRUSTED_ORIGINS` for the deployment.
- `OPENAI_API_KEY` only if the assistant is enabled.

Production rejects debug mode and missing required database/key/host settings. Configure secrets through the hosting environment, never Git. Back up the database before migrations and verify restoration procedures.

Photos require a **persistent Railway Volume attached to the web service**. The application uses `RAILWAY_VOLUME_MOUNT_PATH` and checks for an actual mount; uploads are rejected without persistent storage. Do not substitute an ephemeral folder or publicly serve the private media directory. Database and photo-volume backups must be managed together. The repository alone does not provision or verify these hosting settings.

## Development status and limitations

- Fishing recommendations are heuristic assessments, not guaranteed catches or boating safety advice. Forecast availability and public geocoder coverage vary.
- The structured fishing knowledge catalog and schema validator are a **foundation only**. Species rule lists and the source catalog are currently empty; this knowledge base is not connected to the assistant. See [knowledge documentation](fishinglog/knowledge/README.md).
- Further publication hardening includes authentication/registration abuse controls and dependency security review. Passing tests is not a complete security audit.
- A project-wide license has not yet been selected. Bundled Leaflet retains its own license and maps display the required OpenStreetMap attribution.

Development continues with an emphasis on explainable recommendations, privacy, test coverage and practical mobile use.
