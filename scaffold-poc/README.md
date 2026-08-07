# Camera-first sidewalk-shed POC

Observed on 2026-08-07 from the 38 online NYC DOT cameras within one mile of
40.734717, -73.990696 (the point that was open in Google Maps).

## Result

The scan found two **strong unpermitted-shed candidates**. This proves the
camera-first workflow, but it does not by itself establish a legal violation.
Both cases must stop at a human-review gate because the remaining uncertainty
is whether the visible shed is filed under an adjoining BIN/lot or a very recent
permit has not reached Open Data yet.

The automated acceptance rules used here were:

1. A DOT frame visibly contains a sidewalk shed.
2. Camera direction and the structure's side of the street match a PLUTO lot.
3. The lot/BIN has no unexpired `Sidewalk Shed` or `Supported Scaffold` permit
   in DOB NOW Build Approved Permits.
4. The legacy DOB Permit Issuance table also has no unexpired `SH`/`SF` permit.
5. The system emits `HUMAN_REVIEW_REQUIRED`; it never labels an owner illegal
   or submits a complaint automatically.

## Case 1 — 223 Second Avenue

- Candidate lot: BBL `1-00469-0030`, PLUTO address `223 2 AVENUE`, BIN
  `1006906`.
- Camera: `2 Ave @ E 14 St`, ID
  `02d7db8e-481d-477e-9cdb-a2b6c6ec1ca3`, facing south.
- Frame time: 2026-08-07 18:29:25 EDT.
- Location match: the lot centroid is about 46 m from the camera; the visible
  shed begins on the east/left side immediately south of the camera, matching
  the 223 Second Avenue frontage.
- DOB NOW result: zero Sidewalk Shed or Supported Scaffold permit rows for
  block 469 / lot 30.
- Legacy result: the newest shed permit specifically at 223 Second Avenue was
  job `140561675`, issued 2016-10-12 and expired 2017-10-12.
- Disposition: `HUMAN_REVIEW_REQUIRED`, high-priority candidate.

Evidence:

- [DOT frame](evidence/case-1-223-second-ave/dot-camera-4x.jpg)
- [Camera metadata](evidence/case-1-223-second-ave/camera-metadata.json)
- [PLUTO lot match](evidence/case-1-223-second-ave/pluto-lot.json)
- [DOB NOW permit query result](evidence/case-1-223-second-ave/dob-now-shed-permits.json)
- [Legacy permit rows](evidence/case-1-223-second-ave/legacy-shed-permits.json)

## Case 2 — 74–78 Eighth Avenue / 254–256 West 14th Street

- Candidate lot: BBL `1-00618-0005`, PLUTO address `74 8 AVENUE`. The tax lot
  has several BIN/frontage aliases, including 74/76/78 Eighth Avenue and
  254/256 West 14th Street.
- Camera: `8 Ave @ 14 St`, ID
  `3dc1adcd-7a47-45c3-a667-9d8fae9fdcd0`, facing east.
- Frame time: 2026-08-07 18:29:23 EDT.
- Location match: the lot centroid is about 35 m from the camera. The candidate
  is the shed on the south/right side of the east-facing view.
- DOB NOW result: the newest row on the candidate lot is permit
  `M00187126-I1-SH`, issued 2022-04-04, expired 2023-04-01, and marked
  `Signed-off`. No later unexpired shed/scaffold permit appears for the lot.
- Control: the shed on the opposite/north side at 80 Eighth Avenue has a valid
  permit (`M00950093-I1-SH`) through 2026-12-31. This is useful proof that the
  validator can distinguish two structures in the same intersection instead
  of flagging every shed it sees.
- Disposition: `HUMAN_REVIEW_REQUIRED`, high-priority candidate.

Evidence:

- [DOT frame](evidence/case-2-74-78-eighth-ave/dot-camera-4x.jpg)
- [Camera metadata](evidence/case-2-74-78-eighth-ave/camera-metadata.json)
- [PLUTO lot match](evidence/case-2-74-78-eighth-ave/pluto-lot.json)
- [DOB NOW permit rows](evidence/case-2-74-78-eighth-ave/dob-now-shed-permits.json)
- [Legacy permit rows](evidence/case-2-74-78-eighth-ave/legacy-shed-permits.json)
- [Valid opposite-side control](evidence/case-2-74-78-eighth-ave/legal-control-80-eighth-ave.json)

## Recommended product flow

`DOT frame -> shed detector -> street-side/lot matcher -> current-permit join ->
typed evidence packet -> human approval`

The hackathon demo should show three lanes: green for a current permit, red for
no current permit, and amber for uncertain geolocation or stale imagery. The
human reviewer sees the frame, lot outline, latest permit row, and rejection
reasons before approving a case.

## Data sources

- NYC DOT traffic-camera API
- NYC PLUTO (`64uk-42ks`)
- DOB NOW Build Approved Permits (`rbx6-tga4`)
- DOB Permit Issuance (`ipu4-2q9a`)
- DOB ECB Violations (`6bgk-3dad`)
