const state = { snapshot: null, map: null, markers: new Map(), activeCase: null };

const statusMeta = (status) => ({
  valid_permit: { label: "Permit valid", cls: "valid" },
  no_current_permit_found: { label: "Review permit gap", cls: "review" },
  location_unresolved: { label: "Location unresolved", cls: "unresolved" },
}[status] || { label: status, cls: "unresolved" });

function formatDate(value) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function initializeMap(snapshot) {
  state.map = L.map("map", { zoomControl: false, attributionControl: false }).setView([snapshot.center_latitude, snapshot.center_longitude], 14);
  L.control.zoom({ position: "bottomright" }).addTo(state.map);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", { maxZoom: 20 }).addTo(state.map);
  L.circle([snapshot.center_latitude, snapshot.center_longitude], { radius: snapshot.radius_m, color: "#c8ff4d", weight: 1, fillColor: "#c8ff4d", fillOpacity: .025, dashArray: "5 8" }).addTo(state.map);
  snapshot.cases.forEach(item => {
    const meta = statusMeta(item.status);
    const icon = L.divIcon({ className: "", html: `<div class="marker ${meta.cls}"></div>`, iconSize: [20,20], iconAnchor: [10,10] });
    const marker = L.marker([item.lot.latitude, item.lot.longitude], { icon }).addTo(state.map).on("click", () => openCase(item.case_id));
    marker.bindTooltip(item.title, { direction: "top", offset: [0,-8] });
    state.markers.set(item.case_id, marker);
  });
}

function renderMetrics(snapshot) {
  const values = [snapshot.metrics.frames_matched, snapshot.metrics.sheds_detected, snapshot.metrics.permit_gaps, snapshot.metrics.controls];
  document.querySelectorAll("#metrics article strong").forEach((el, index) => el.textContent = values[index]);
  document.getElementById("snapshot-time").textContent = formatDate(snapshot.observed_at);
  document.getElementById("model-pill").textContent = snapshot.model_provider;
}

function renderCases(snapshot) {
  const list = document.getElementById("case-list");
  const pending = snapshot.cases.filter(item => item.decision === "pending" && !item.is_control).length;
  document.getElementById("queue-count").textContent = `${pending} pending`;
  list.innerHTML = snapshot.cases.map(item => {
    const meta = statusMeta(item.status);
    const permit = item.permit_evidence.current_permit || item.permit_evidence.latest_record;
    const decision = item.decision !== "pending" ? ` · ${item.decision.toUpperCase()}` : "";
    return `<article class="case-card" data-case-id="${item.case_id}">
      <div class="case-top"><div><span class="kicker">${item.is_control ? "CONTROL" : `CONFIDENCE ${Math.round(item.detection.confidence*100)}%`}</span><h3>${item.title}</h3></div><span class="status ${meta.cls}">${meta.label}</span></div>
      <p>${item.permit_evidence.explanation}</p>
      <div class="case-meta"><span>BBL ${item.lot.bbl}</span><span>${permit?.expiration_date || "NO PERMIT"}${decision}</span></div>
    </article>`;
  }).join("");
  list.querySelectorAll(".case-card").forEach(card => card.addEventListener("click", () => openCase(card.dataset.caseId)));
}

function boxStyle(box) {
  return `top:${box.ymin/10}%;left:${box.xmin/10}%;width:${(box.xmax-box.xmin)/10}%;height:${(box.ymax-box.ymin)/10}%`;
}

function renderDrawer(item) {
  const meta = statusMeta(item.status);
  const permit = item.permit_evidence.current_permit || item.permit_evidence.latest_record;
  const decision = item.decision !== "pending" ? `<div class="decision-banner">REVIEW DECISION · ${item.decision.toUpperCase()}${item.review_note ? ` — ${item.review_note}` : ""}</div>` : "";
  const action = item.is_control ? "" : `<div class="review-actions"><textarea id="review-note" placeholder="Optional reviewer note…">${item.review_note || ""}</textarea><button class="dismiss" data-decision="dismiss">Dismiss candidate</button><button class="approve" data-decision="approve">Approve for follow-up</button></div>`;
  document.getElementById("drawer-content").innerHTML = `
    <div class="drawer-head"><span class="status ${meta.cls}">${meta.label}</span><h2>${item.title}</h2><p class="lede">${item.lot.address_aliases.join(" · ")}</p></div>
    ${decision}
    <div class="evidence-image"><img src="${item.frame.image_path}" alt="NYC DOT camera evidence"><div class="bbox" style="${boxStyle(item.detection.box)}"></div></div>
    <div class="detail-grid">
      <div class="detail"><span>Vision confidence</span><strong>${Math.round(item.detection.confidence*100)}% · ${item.detection.provider}</strong></div>
      <div class="detail"><span>Location match</span><strong>${Math.round(item.lot.confidence*100)}% · ${item.lot.distance_from_camera_m} m</strong></div>
      <div class="detail"><span>Tax lot</span><strong>BBL ${item.lot.bbl}</strong></div>
      <div class="detail"><span>Latest permit</span><strong>${permit ? `${permit.permit_id} · ${permit.expiration_date}` : "None found"}</strong></div>
    </div>
    <div class="evidence-block"><h4>WHY IT WAS FLAGGED</h4><p>${item.detection.visual_reason}</p><p>${item.permit_evidence.explanation}</p></div>
    <div class="evidence-block"><h4>ENFORCEMENT CONTEXT</h4><p>${item.ecb_context}</p></div>
    <div class="evidence-block"><h4>HUMAN REVIEW GATE</h4><ul>${item.reviewer_questions.map(q => `<li>${q}</li>`).join("")}</ul></div>
    ${action}`;
  document.querySelectorAll("[data-decision]").forEach(btn => btn.addEventListener("click", () => submitDecision(item.case_id, btn.dataset.decision)));
}

async function openCase(caseId) {
  const response = await fetch(`/api/cases/${caseId}`);
  const item = await response.json();
  state.activeCase = caseId;
  renderDrawer(item);
  document.getElementById("drawer").classList.add("open");
  document.getElementById("drawer-backdrop").classList.add("open");
  document.getElementById("drawer").setAttribute("aria-hidden", "false");
  state.map?.panTo([item.lot.latitude, item.lot.longitude]);
}

function closeDrawer() {
  document.getElementById("drawer").classList.remove("open");
  document.getElementById("drawer-backdrop").classList.remove("open");
  document.getElementById("drawer").setAttribute("aria-hidden", "true");
}

async function submitDecision(caseId, decision) {
  const note = document.getElementById("review-note")?.value || null;
  const response = await fetch(`/api/cases/${caseId}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, note }) });
  if (!response.ok) return;
  await loadSnapshot(false);
  await openCase(caseId);
}

async function loadSnapshot(first = true) {
  const response = await fetch("/api/snapshot");
  if (!response.ok) throw new Error("Snapshot unavailable");
  state.snapshot = await response.json();
  renderMetrics(state.snapshot);
  renderCases(state.snapshot);
  if (first) initializeMap(state.snapshot);
}

document.getElementById("drawer-close").addEventListener("click", closeDrawer);
document.getElementById("drawer-backdrop").addEventListener("click", closeDrawer);
document.addEventListener("keydown", event => { if (event.key === "Escape") closeDrawer(); });
loadSnapshot().catch(error => { document.getElementById("case-list").innerHTML = `<div class="loading">${error.message}</div>`; });
