# NYC Vision Hack v.2 — working context

Captured August 7, 2026 from the authenticated hackathon portal and participant handbook.

## What we have to ship

- Build an AI/vision agent tied clearly to a real NYC problem, quirk, or opportunity.
- Use a live or public city feed responsibly. Judges specifically want the demo running on real feeds.
- Deploy the agent on **Google Cloud Run**. This is a binary eligibility gate, not merely a judging bonus.
- Publish a **public GitHub repository** with a README that explains the story, architecture, data sources, setup, tradeoffs, and limitations.
- Submit by **8:30 PM EDT**; demos begin at 8:45 PM.
- Teams may have up to four people. Our portal team is currently `localhost`.

## Submission mechanics

Only the team lead can edit/finalize the submission. Coordinate with the lead before the lock.

Required items:

1. Project name
2. Project description — should name the technologies and explain the NYC impact against the judging criteria
3. Products/tools used
4. A contribution statement for every teammate

Optional but valuable:

- Up to a 2-minute public/unlisted YouTube or shareable Loom video
- GitHub repository and deployed-project links
- Prior-work disclosure
- Social posts tagging AI Tinkerers and sponsors

## Judging rubric

| Criterion | What earns the top score |
| --- | --- |
| Working demo | Solid, visible behavior on real feeds |
| NYC relevance | A sharp fit that could only make sense in NYC |
| Usefulness or insight | A clear “oh wow” result: clearer, faster, safer, cheaper, or more legible |
| Technical execution | Polished enough to understand; thoughtful architecture and tradeoffs |
| Cloud Run | Mandatory to submit |
| Open source | Clean public repo and a README that tells the story |

## Time-boxed build strategy

The safest architecture is deliberately small:

```text
NYC live/public feed
        ↓
Cloud Run service (polling/orchestration + API + lightweight UI)
        ↓
Roboflow hosted inference or a pre-trained Universe model
        ↓
Structured observations / small rolling summary
        ↓
One visually obvious NYC insight or agent action
```

Avoid training a model tonight unless the chosen concept absolutely requires it. Roboflow Workflows or a pre-trained Universe model keeps the Cloud Run container light and reduces deployment risk.

Deploy a hello-world Cloud Run service first, then iterate behind the live URL. Keep a short fallback recording or cached frame sequence for the stage demo, because a camera/feed can go dark at 8:45.

## Best primary live feed: NYC DOT cameras

- Camera inventory: <https://webcams.nyctmc.org/api/cameras>
- Current still for a camera: `https://webcams.nyctmc.org/api/cameras/{id}/image`
- Map: <https://webcams.nyctmc.org/map>
- Camera list: <https://webcams.nyctmc.org/cameras-list>

Live verification at roughly 5:00 PM EDT:

- 968 cameras returned
- 964 marked online
- `isOnline` is the string `"true"`, not a JSON boolean
- Each record includes `id`, `name`, `latitude`, `longitude`, `area`, `isOnline`, and `imageUrl`
- The still endpoint returned a JPEG successfully; polling every few seconds creates a low-frame-rate stream

Minimal fetch pattern:

```python
import requests

cameras = requests.get(
    "https://webcams.nyctmc.org/api/cameras", timeout=15
).json()
online = [camera for camera in cameras if camera.get("isOnline") == "true"]

frame = requests.get(online[0]["imageUrl"], timeout=15).content
```

## Other data directions from the handbook

Real-time or operational:

- MTA BusTime GTFS-Realtime feeds
- NYC fire dispatch and emergency-response incidents
- NYISO real-time electricity dashboard
- MTA accessible-station platform availability
- BirdCast live migration
- OpenSky live air traffic
- MarineCadastre vessel traffic

Static/historical context that can enrich a live agent:

- 311 rodent complaints
- Mapillary street imagery
- NYC trees and tree-canopy layers
- NYC truck routes and parcel-delivery research
- Outdoor public art and historical-sign inventories
- 1940s tax photos and current building imagery
- Welikia/Mannahatta historical ecology
- LiDAR/topobathymetry and landmarks data

## Idea-selection filter

A good choice should pass all of these quickly:

- **Visual in five seconds:** the audience immediately sees what was detected or inferred.
- **Agent, not dashboard:** it interprets, prioritizes, explains, recommends, or triggers a bounded action.
- **Hyperlocal NYC hook:** street behavior, mobility, access, infrastructure, public realm, or a distinctly NYC quirk.
- **No custom-data dependency:** the first demo works with a pre-trained model or multimodal model.
- **Robust demo path:** one known-good camera/feed plus a cached fallback.
- **One sentence of value:** “It helps X do Y by noticing Z.”
- **Privacy-aware:** do not identify people; minimize/blur faces and plates where relevant; retain derived counts/events instead of raw frames.

## Sources

- Event portal: <https://nyc.aitinkerers.org/hackathons/h_zvqhzy3dMEY>
- Participant handbook: <https://nyc.aitinkerers.org/hackathons/h_zvqhzy3dMEY/handbook>
- Submission page: <https://nyc.aitinkerers.org/hackathons/h_zvqhzy3dMEY/entries>
- Google Cloud temporary-account README: <https://docs.google.com/document/d/1V52oRMe25xifRafZimMFTlNQyxffwy8QEfcs3dtwrQQ/edit?usp=sharing>
- Roboflow docs: <https://docs.roboflow.com/>
- Roboflow Workflows: <https://docs.roboflow.com/workflows>
- Roboflow Universe: <https://universe.roboflow.com/>
