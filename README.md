# Shedwatch NYC

**See the shed. Check the permit.**

Shedwatch turns a daily snapshot of NYC DOT traffic cameras into a
human-reviewed queue of sidewalk sheds whose permit status deserves a closer
look. Gemini finds the physical structure; deterministic NYC Open Data checks
the permit. A reviewer—not the model—decides whether a case merits follow-up.

Built for NYC Vision Hack v.2 and deployed on Google Cloud Run.

**Live demo:** <https://shedwatch-nyc-187000325658.us-east1.run.app>

## Citywide demo result

The August 7 rain snapshot contains 964 JPEGs. The latest Cloud Run execution
matched 959 frames to 963 online cameras and published this measured funnel:

- 96 of 957 non-POC frames completed high-recall screening before the Gemini
  API's spend-rate limit stopped the remaining batches: 61 no, 26 possible,
  and 9 likely.
- All 35 likely/possible frames advanced to full single-image detection and an
  adversarial vision check requiring both a rigid deck and support posts.
- Six survived and had an active DOB shed permit within 120 metres. They remain
  blue, not green, until the image frontage is assigned to that permit's lot.
- The live header and `GET /api/scan-status` expose the exact screened count.

The job is resumable; unprocessed frames are not silently called clear. The
959 dashboard metric means camera/frame records matched, not 959 completed
Gemini inspections.

The explicitly resolved Union Square proof cases remain the legal-triage
acceptance set:

| Location | Camera finding | Latest matching permit | Result |
| --- | --- | --- | --- |
| 223 Second Avenue | Gemini detects a shed on the east sidewalk | Expired 2017-10-12 | Human review |
| 74–78 Eighth Avenue | Gemini detects the south-side corner shed | Signed off; expired 2023-04-01 | Human review |
| 80 Eighth Avenue | Permit-only control; no vision box asserted | Work permit valid through 2026-08-20; active-registry job through 2026-12-31 | Permitted control |

“No current permit found” is a screening result, not an adjudication of
illegality. Lot attribution, newly issued permits, and posted permit numbers
must be checked by a person.

## Verify a result in 60 seconds

Open a case and use the four buttons at the top of its evidence drawer:

1. Compare the boxed saved image with **Fresh DOT frame**.
2. Use **Street View** to confirm the structure belongs to the named frontage.
3. Open **DOB profile** and confirm the BIN shown by Shedwatch.
4. Open **Exact permit row**. This is the city's machine-readable record for
   the exact permit/job, not a search-engine result.

The release acceptance rows are:

- 223 Second Avenue: legacy permit `140561675`, `ISSUED`, expired
  `2017-10-12`; no matching BIN in the daily active-shed registry.
- 74–78 Eighth Avenue: DOB NOW permit `M00187126-I1-SH`, `Signed-off`, expired
  `2023-04-01`; no matching BIN in the daily active-shed registry.
- 80 Eighth Avenue: DOB NOW permit `M00950093-I1-SH`, `Permit Issued`, valid
  through `2026-08-20`; the daily active registry lists its job through
  `2026-12-31`. Those dates come from two different official sources and are
  intentionally shown separately.

Every permit ID in the audit table is also a direct link to its exact official
JSON row, and the displayed dates are parsed from that linked response.

## Architecture

```text
Private Cloud Storage bucket
  input/964 original DOT JPEGs
        │
        ▼
Cloud Run Job: shedwatch-citywide-scan
  camera matching → Gemini screen → Gemini detection → adversarial check
        │
        ├─ explicit camera/frontage match for the POC
        ├─ PLUTO BBL + BIN aliases
        └─ deterministic DOB NOW + legacy + daily active-registry checks
        │
        ▼
Private Cloud Storage output
  scan-snapshot.json + selected evidence JPEGs + resumable checkpoints
        │
        ▼
Cloud Run service: shedwatch-nyc
  read-only snapshot API → map + evidence review queue → approve / dismiss
```

The production web service does not run vision or create findings. It mounts and
renders artifacts created by the separate Cloud Run Job. A cloud-generated
snapshot and its selected evidence frames are also bundled as a stage-demo
fallback if the mounted artifact is temporarily unavailable.

## Technology

- FastAPI, Pydantic v2, and a dependency-free JavaScript frontend
- Gemini structured image understanding through `google-genai`
- Leaflet and CARTO/OSM map tiles
- NYC DOT Traffic Cameras
- DOB Active Sidewalk Shed Permits daily registry and map
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

Run the resumable whole-city pipeline with:

```bash
python -m app.citywide
```

It checkpoints high-recall screening and adversarial confirmations under
`app/data/`, then copies only review evidence into the deployable static assets.

## API

- `GET /healthz` — container-local health check
- `GET /api/healthz` — externally reachable Cloud Run health check
- `GET /api/snapshot`
- `GET /api/scan-status`
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

All authoritative processing happens in the `shedwatch-citywide-scan` Cloud Run
Job. The job mounts the private input/output bucket and uses the Gemini key from
Secret Manager:

```bash
gcloud run jobs execute shedwatch-citywide-scan \
  --project cloudrun-hack26nyc-4331 \
  --region us-east1 \
  --wait
```

The public viewer is built directly from this repository and mounts only the
job's output:

```bash
gcloud run deploy shedwatch-nyc \
  --project cloudrun-hack26nyc-4331 \
  --source . \
  --region us-east1 \
  --allow-unauthenticated \
  --cpu 1 \
  --memory 512Mi \
  --max-instances 2 \
  --set-env-vars SNAPSHOT_PATH=/mnt/shedwatch/output/scan-snapshot.json,EVIDENCE_DIR=/mnt/shedwatch/output/frames \
  --add-volume name=shedwatch-data,type=cloud-storage,bucket=cloudrun-hack26nyc-4331-shedwatch \
  --add-volume-mount volume=shedwatch-data,mount-path=/mnt/shedwatch
```

The public service does not receive the Gemini key. Its process only validates
and serves the Cloud Run Job's typed JSON output.

## Limitations and responsible use

- Traffic cameras are low-resolution, weather-sensitive, and may point away
  from the named intersection.
- Gemini detects structures but does not decide legal status.
- The POC uses explicit frontage mappings for the two known cases; automated
  camera-pixel-to-tax-lot attribution is future work.
- Open Data can lag a newly issued permit.
- The latest citywide execution hit Gemini's spend-rate limit after 96 frames;
  the remaining 861 are visibly pending rather than classified.
- A reviewer must verify the frontage, adjoining BINs, and posted permit before
  any escalation.
- No complaint, enforcement action, or permit filing is submitted by this app.

## Daily production path after the hackathon

Trigger `shedwatch-citywide-scan` daily with Cloud Scheduler after the latest
camera capture has landed in `input/`. Store dated snapshots before replacing
the latest output, and move review decisions from process memory to Firestore.
