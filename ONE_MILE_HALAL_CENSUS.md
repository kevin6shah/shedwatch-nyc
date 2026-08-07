# One-mile DOT halal-cart census

Run: 2026-08-07, 17:53-17:57 EDT

## Bottom line

**One likely halal cart was discovered in the DOT imagery and could not be matched to an exact Google Maps place.** This run does **not** support a claim that five or more Google-Maps-missing halal carts are easily discoverable from the public DOT snapshots in this one-mile area.

The conservative counts are:

| Result | Count |
| --- | ---: |
| Clear live cart/food-stand candidates discovered in DOT frames | 1 |
| Candidates independently validated as a halal cart | 1 |
| Validated candidates without an exact Google Maps listing | 1 |
| Additional ambiguous sidewalk objects rejected | Several |

## Search boundary and method

- Center: device location near Houston Street and Broadway (40.72517, -73.99662).
- Radius: 1 statute mile / 1,609.344 m.
- DOT cameras returned as online inside the radius: 57.
- Evidence capture: one same-minute snapshot from all 57 cameras, followed by a second snapshot to rule out transient vehicle/umbrella confusion.
- Discovery rule: a candidate had to appear in DOT imagery before any registry or web lookup was used.
- Exclusion rule: tents, sidewalk dining umbrellas, kiosks, vehicle roofs, and objects too small to classify were not counted.
- Google Maps rule: nearby search results did not disqualify a candidate unless the pin matched the same name/location; nearby but spatially distinct carts were treated as different entities.

The three contact sheets cover every camera inspected:

- [Cameras 1-20](evidence/one-mile-halal-census/contact-sheet-01.jpg)
- [Cameras 21-40](evidence/one-mile-halal-census/contact-sheet-02.jpg)
- [Cameras 41-57](evidence/one-mile-halal-census/contact-sheet-03.jpg)
- [Camera metadata and distances](evidence/one-mile-halal-census/cameras.json)

## The one surviving candidate

### Union Square Halal Food — likely match

| Field | Evidence |
| --- | --- |
| DOT discovery | Yellow/blue cart-style umbrella persists at the lower-right edge of the live frame from **Union Sq @ 14 St**. |
| Camera | ID `d47d2f63-cdc1-4f28-bc4c-e64ac07e4f1d`; 40.73483, -73.99087; 1,178 m / 0.73 mi from the search center. |
| Live captures | 17:53:43 and 17:54:29 EDT; object remains fixed while traffic changes. |
| Identity validator | Over Rice lists **Union Square Halal Food** at 14th Street and Broadway; its coordinate is approximately 19.3 m from the DOT camera. |
| Maps test | Exact-name search returned other halal carts, but none at the candidate coordinate. The nearest returned listings were **100 Percent Halal Food** (80 m away), **14 Street Halal Food** (98 m), **The Halal Kitchen** (115 m), and **Santa Halal Food** (185 m). Navigating to the candidate coordinate resolved to the coordinate rather than a place card. |
| Verdict | **Likely halal; no exact Google Maps listing found.** The cart is real in the live DOT frame, but its name is not readable, so identity is medium-confidence rather than OCR-confirmed. |

Evidence:

- [Raw DOT frame](evidence/one-mile-halal-census/union-square-dot-frame.jpg)
- [Enlarged DOT frame](evidence/one-mile-halal-census/union-square-dot-frame-4x.jpg)
- [Earlier independent capture and crop](evidence/union-square-halal/dot-cart-crop.jpg)

## Why the count is not higher

The failure mode is camera geometry, not necessarily cart scarcity. The public frames are only 352 x 240 pixels, most cameras point along traffic lanes, and the sidewalk immediately below a camera is commonly cropped out. For example, an external cart guide places **#1 Soho Halal Guy** at Houston Street and Broadway—almost exactly at the search center—but the Houston/Broadway DOT camera faces south over the roadway and does not visibly capture that cart. It was therefore excluded under the camera-first rule.

The same problem affected cameras near other independently known carts around 14th Street: the relevant corner was outside the frame, occluded, or too small to classify. Counting those would turn the registry into the discovery source and defeat the experiment.

## Product implication

This is still a useful POC, but the winning version should not promise a complete census from one instantaneous DOT sweep. The defensible product is a **camera-triggered change detector**:

1. Monitor cameras whose fields of view actually include known vending zones.
2. Detect a persistent cart/umbrella object across multiple frames.
3. Associate it with a precise corner and compare it with the last-seen record.
4. Ask an agent to resolve identity using cart registries, social posts, OCR when available, and Google Maps proximity—not exact-name matching alone.
5. Publish confidence, last-seen time, and evidence rather than pretending every cart is confirmed.

The current run proves the pipeline can find one real Maps gap, but it also shows that camera coverage/angle is the main bottleneck to reaching five in this neighborhood.
