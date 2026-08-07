# Shedwatch NYC

**See the shed. Check the permit.**

Shedwatch turns a daily snapshot of NYC DOT traffic cameras into a
human-reviewed queue of sidewalk sheds whose permit status deserves a closer
look. Gemini finds the physical structure; deterministic NYC Open Data checks
the permit. A reviewer—not the model—decides whether a case merits follow-up.

Built for NYC Vision Hack v.2 and deployed on Google Cloud Run.

**Live demo:** <https://shedwatch-nyc-187000325658.us-east1.run.app>

## Demo result

The one-mile Union Square pilot matched 38 DOT cameras from a 964-camera daily
snapshot. It surfaces two high-priority permit-gap candidates and one useful
control:

| Location | Camera finding | Latest matching permit | Result |
| --- | --- | --- | --- |
| 223 Second Avenue | Gemini detects a shed on the east sidewalk | Expired 2017-10-12 | Human review |
| 74–78 Eighth Avenue | Gemini detects the south-side corner shed | Signed off; expired 2023-04-01 | Human review |
| 80 Eighth Avenue | Opposite-side shed in the same intersection | Valid through 2026-12-31 | Permitted control |

“No current permit found” is a screening result, not an adjudication of
illegality. Lot attribution, newly issued permits, and posted permit numbers
must be checked by a person.

## Architecture

```text
Daily DOT JPEG snapshot
        │
        ├─ camera-name matching + one-mile geofence
        │
        ▼
Gemini Flash structured vision
  shed boxes, confidence, visual reason
        │
        ▼
Explicit camera/frontage match for the POC
  PLUTO BBL + BIN aliases
        │
        ▼
Deterministic permit validator
  DOB NOW + legacy permits + ECB context
        │
        ▼
FastAPI snapshot API → map + evidence review queue
                         approve / dismiss
```

The deployed app bundles the latest derived snapshot and its 38 pilot frames,
so the stage demo continues to work if a camera or upstream API is unavailable.

## Technology

- FastAPI, Pydantic v2, and a dependency-free JavaScript frontend
- Gemini structured image understanding through `google-genai`
- Leaflet and CARTO/OSM map tiles
- NYC DOT Traffic Cameras
- NYC PLUTO (`64uk-42ks`)
- DOB NOW Build Approved Permits (`rbx6-tga4`)
- DOB Permit Issuance (`ipu4-2q9a`)
- DOB ECB Violations (`6bgk-3dad`)
- Google Cloud Run

## Run locally

Python 3.11+ is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Add your GEMINI_API_KEY to .env
python -m app.scanner --mode gemini --refresh-permits
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>.

The scanner reads `/Users/kevinshah/Downloads/frames-rain` by default. Override
it with `FRAME_DIR`. Targeted mode sends only the mapped proof cameras to
Gemini; add `--scan-all` to analyze every matched frame in the radius.

```bash
FRAME_DIR=/path/to/daily/frames \
  python -m app.scanner --mode gemini --refresh-permits --scan-all
```

For deterministic development without model calls:

```bash
python -m app.scanner --mode fixture --refresh-permits
```

## API

- `GET /healthz` — container-local health check
- `GET /api/healthz` — externally reachable Cloud Run health check
- `GET /api/snapshot`
- `GET /api/cases/{case_id}`
- `POST /api/cases/{case_id}/decision`

Decision body:

```json
{"decision":"approve","note":"Frontage visually confirmed"}
```

Review decisions are intentionally in memory for the hackathon build and may
reset when a Cloud Run instance restarts.

## Tests

```bash
python -m pytest -q
```

The suite covers model-schema guardrails, radius matching, permit-expiration
rules, the known candidate/control classifications, and review actions.

## Cloud Run

The production service is built directly from this repository:

```bash
gcloud run deploy shedwatch-nyc \
  --project cloudrun-hack26nyc-4331 \
  --source . \
  --region us-east1 \
  --allow-unauthenticated \
  --cpu 1 \
  --memory 512Mi \
  --max-instances 2 \
  --set-env-vars GEMINI_MODEL=gemini-3.6-flash \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest
```

The service does not need the API key to serve its bundled snapshot. The secret
is only required when running a new Gemini scan.

## Limitations and responsible use

- Traffic cameras are low-resolution, weather-sensitive, and may point away
  from the named intersection.
- Gemini detects structures but does not decide legal status.
- The POC uses explicit frontage mappings for the two known cases; automated
  camera-pixel-to-tax-lot attribution is future work.
- Open Data can lag a newly issued permit.
- A reviewer must verify the frontage, adjoining BINs, and posted permit before
  any escalation.
- No complaint, enforcement action, or permit filing is submitted by this app.

## Daily production path after the hackathon

Move raw frames to Cloud Storage, run the same scanner as a daily Cloud Run Job,
write the derived snapshot to Cloud Storage or Firestore, and schedule it with
Cloud Scheduler. The web service and its typed API do not need to change.
