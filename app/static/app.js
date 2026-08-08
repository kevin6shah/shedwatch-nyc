const state = { snapshot: null, map: null, markers: new Map(), activeCase: null };

const statusMeta = (status) => ({
  valid_permit: { label: "Permit valid", cls: "valid" },
  permit_nearby_unverified: { label: "Permit nearby · verify frontage", cls: "nearby" },
  no_current_permit_found: { label: "Review permit gap", cls: "review" },
  location_unresolved: { label: "Location unresolved", cls: "unresolved" },
}[status] || { label: status, cls: "unresolved" });

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
}

function formatDate(value) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function exactRecordUrl(record) {
  if (!record) return null;
  if (record.source === "dob_now" && record.issued_date) {
    const query = new URLSearchParams({
      "$where": `work_permit="${record.permit_id}" and issued_date="${record.issued_date}T00:00:00.000"`,
      "$limit": "10",
    });
    return `https://data.cityofnewyork.us/resource/rbx6-tga4.json?${query}`;
  }
  return record.record_url;
}

function initializeMap(snapshot) {
  state.map = L.map("map", { zoomControl: false, attributionControl: false }).setView([snapshot.center_latitude, snapshot.center_longitude], snapshot.scope === "citywide" ? 10 : 14);
  L.control.zoom({ position: "bottomright" }).addTo(state.map);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", { maxZoom: 20 }).addTo(state.map);
  if (snapshot.scope !== "citywide") L.circle([snapshot.center_latitude, snapshot.center_longitude], { radius: snapshot.radius_m, color: "#c8ff4d", weight: 1, fillColor: "#c8ff4d", fillOpacity: .025, dashArray: "5 8" }).addTo(state.map);
  const bounds = [];
  snapshot.cases.forEach(item => {
    const meta = statusMeta(item.status);
    const icon = L.divIcon({ className: "", html: `<div class="marker ${meta.cls}"></div>`, iconSize: [20,20], iconAnchor: [10,10] });
    const marker = L.marker([item.lot.latitude, item.lot.longitude], { icon }).addTo(state.map).on("click", () => openCase(item.case_id));
    marker.bindTooltip(escapeHtml(item.title), { direction: "top", offset: [0,-8] });
    state.markers.set(item.case_id, marker);
    bounds.push([item.lot.latitude, item.lot.longitude]);
  });
  if (snapshot.scope === "citywide" && bounds.length) state.map.fitBounds(bounds, { padding: [24, 24], maxZoom: 13 });
}

function renderMetrics(snapshot) {
  const values = [snapshot.metrics.frames_matched, snapshot.metrics.sheds_detected, snapshot.metrics.permit_gaps, snapshot.scope === "citywide" ? snapshot.metrics.permit_nearby : snapshot.metrics.controls];
  document.querySelectorAll("#metrics article strong").forEach((el, index) => el.textContent = values[index]);
  document.getElementById("snapshot-time").textContent = formatDate(snapshot.observed_at);
  document.getElementById("model-pill").textContent = snapshot.model_provider;
  document.getElementById("scope-label").textContent = snapshot.scope === "citywide" ? "NYC · ALL AVAILABLE CAMERAS" : "UNION SQUARE · 1 MILE";
  document.getElementById("map-title").textContent = snapshot.scope === "citywide" ? "Citywide scan" : "One-mile pilot";
  document.getElementById("camera-caption").textContent = snapshot.scope === "citywide" ? "matched citywide frames" : "inside pilot radius";
  document.getElementById("fourth-label").textContent = snapshot.scope === "citywide" ? "PERMIT NEARBY" : "VALID CONTROL";
  document.getElementById("fourth-caption").textContent = snapshot.scope === "citywide" ? "frontage needs verification" : "permit confirmed";
  document.getElementById("map-note").textContent = snapshot.scope === "citywide" ? "Citywide leads use camera coordinates and a 120 m daily active-permit search. Red cases have an explicit tax-lot match; amber cases require frontage attribution." : "DOT frames are matched to lots using camera direction, street side, and explicit POC frontage mappings.";
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
      <div class="case-top"><div><span class="kicker">${item.is_control ? "CONTROL" : `CONFIDENCE ${Math.round(item.detection.confidence*100)}%`}</span><h3>${escapeHtml(item.title)}</h3></div><span class="status ${meta.cls}">${escapeHtml(meta.label)}</span></div>
      <p>${escapeHtml(item.permit_evidence.explanation)}</p>
      <div class="case-meta"><span>BBL ${escapeHtml(item.lot.bbl)}</span><span>${escapeHtml(permit?.expiration_date || "NO PERMIT")}${decision}</span></div>
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
  const decision = item.decision !== "pending" ? `<div class="decision-banner">REVIEW DECISION · ${escapeHtml(item.decision.toUpperCase())}${item.review_note ? ` — ${escapeHtml(item.review_note)}` : ""}</div>` : "";
  const action = item.is_control ? "" : `<div class="review-actions"><textarea id="review-note" placeholder="Optional reviewer note…">${escapeHtml(item.review_note || "")}</textarea><button class="dismiss" data-decision="dismiss">Dismiss candidate</button><button class="approve" data-decision="approve">Approve for follow-up</button></div>`;
  const records = item.permit_evidence.records || [];
  const recordRows = records.length ? records.map(record => { const url = exactRecordUrl(record); return `<tr><td>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(record.permit_id)} ↗</a>` : escapeHtml(record.permit_id)}</td><td>${escapeHtml(record.source.replaceAll("_", " "))}</td><td>${escapeHtml(record.status)}</td><td>${escapeHtml(record.issued_date || "—")}</td><td>${escapeHtml(record.expiration_date || "—")}</td></tr>`; }).join("") : `<tr><td colspan="5">No matching permit rows returned.</td></tr>`;
  const sourceLinks = (item.permit_evidence.source_links || []).map(link => `<a class="source-link" href="${escapeHtml(link.url)}" target="_blank" rel="noopener"><strong>${escapeHtml(link.label)} ↗</strong><span>${escapeHtml(link.description)}</span></a>`).join("");
  const registryBadge = item.permit_evidence.active_registry_checked ? `<span class="audit-check">✓ DAILY ACTIVE REGISTRY CHECKED · ${item.permit_evidence.active_registry_matches} MATCH${item.permit_evidence.active_registry_matches === 1 ? "" : "ES"}</span>` : `<span class="audit-warn">REGISTRY CHECK UNAVAILABLE</span>`;
  const bin = item.lot.bin_ids?.[0];
  const dobProfile = bin ? `https://a810-bisweb.nyc.gov/bisweb/PropertyProfileOverviewServlet?bin=${encodeURIComponent(bin)}` : null;
  const streetView = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${encodeURIComponent(item.lot.latitude)},${encodeURIComponent(item.lot.longitude)}`;
  const officialQuery = exactRecordUrl(permit) ? { url: exactRecordUrl(permit) } : ((item.permit_evidence.source_links || []).find(link => link.label.startsWith("Exact")) || (item.permit_evidence.source_links || [])[0]);
  const verifyText = {
    no_current_permit_found: "Confirm the boxed shed occupies this BBL, then open the exact permit query and check that no later active SH/SF row exists. Finally look on the fresh frame/site for a posted permit number.",
    valid_permit: `Match the visible shed to permit ${permit?.permit_id || "shown below"}, its address, and expiration date in the official record.`,
    permit_nearby_unverified: "Compare the boxed frontage with the nearby permit address. Do not approve unless Street View, camera direction, or the posted permit number ties them to the same structure.",
    location_unresolved: "Resolve the boxed structure to a building frontage first. No permit conclusion is valid until its BBL/BIN is known.",
  }[item.status];
  const actualPasses = item.case_id.startsWith("citywide-") && item.detection.confirmation_reason ? 2 : 1;
  document.getElementById("drawer-content").innerHTML = `
    <div class="drawer-head"><span class="status ${meta.cls}">${escapeHtml(meta.label)}</span><h2>${escapeHtml(item.title)}</h2><p class="lede">${escapeHtml(item.lot.address_aliases.join(" · "))}</p></div>
    ${decision}
    <div class="evidence-image"><img src="${escapeHtml(item.frame.image_path)}" alt="NYC DOT camera evidence">${item.detection.box ? `<div class="bbox" style="${boxStyle(item.detection.box)}"></div>` : ""}</div>
    <div class="detail-grid">
      <div class="detail"><span>Vision confidence</span><strong>${item.detection.shed_visible ? `${Math.round(item.detection.confidence*100)}% · ${actualPasses} pass${actualPasses === 1 ? "" : "es"}` : "Not asserted · permit-only control"}</strong></div>
      <div class="detail"><span>Location match</span><strong>${Math.round(item.lot.confidence*100)}% · ${item.lot.distance_from_camera_m} m</strong></div>
      <div class="detail"><span>Tax lot</span><strong>BBL ${escapeHtml(item.lot.bbl)}</strong></div>
      <div class="detail"><span>Latest permit</span><strong>${permit ? `${escapeHtml(permit.permit_id)} · ${escapeHtml(permit.expiration_date)}` : "None found"}</strong></div>
    </div>
    <div class="evidence-block verify-fast"><h4>VERIFY IN 60 SECONDS</h4><p>${escapeHtml(verifyText)}</p><div class="verify-links">
      <a href="${escapeHtml(item.frame.live_image_url)}" target="_blank" rel="noopener">1 · Fresh DOT frame ↗</a>
      <a href="${escapeHtml(streetView)}" target="_blank" rel="noopener">2 · Street View ↗</a>
      ${dobProfile ? `<a href="${escapeHtml(dobProfile)}" target="_blank" rel="noopener">3 · DOB profile · BIN ${escapeHtml(bin)} ↗</a>` : ""}
      ${officialQuery ? `<a href="${escapeHtml(officialQuery.url)}" target="_blank" rel="noopener">4 · Exact permit row ↗</a>` : ""}
    </div></div>
    <div class="evidence-block permit-audit"><h4>PERMIT AUDIT TRAIL</h4>${registryBadge}<p>${escapeHtml(item.permit_evidence.records_checked)} records evaluated across ${escapeHtml(item.permit_evidence.sources.join(" · "))}.</p><div class="permit-table-wrap"><table class="permit-table"><thead><tr><th>Permit / job</th><th>Source</th><th>Status</th><th>Issued</th><th>Expires</th></tr></thead><tbody>${recordRows}</tbody></table></div><div class="source-links">${sourceLinks}</div></div>
    <div class="evidence-block"><h4>WHY IT WAS FLAGGED</h4><p>${escapeHtml(item.detection.visual_reason)}</p><p>${escapeHtml(item.permit_evidence.explanation)}</p></div>
    ${item.case_id.startsWith("citywide-") && item.detection.confirmation_reason ? `<div class="evidence-block"><h4>ADVERSARIAL VISION CHECK · ${Math.round(item.detection.confirmation_confidence*100)}%</h4><p>${escapeHtml(item.detection.confirmation_reason)}</p></div>` : ""}
    <div class="evidence-block"><h4>DECISION RULE</h4><p>${escapeHtml(item.permit_evidence.verification_rule)}</p></div>
    <div class="evidence-block"><h4>ENFORCEMENT CONTEXT</h4><p>${escapeHtml(item.ecb_context)}</p></div>
    <div class="evidence-block"><h4>HUMAN REVIEW GATE</h4><ul>${item.reviewer_questions.map(q => `<li>${escapeHtml(q)}</li>`).join("")}</ul></div>
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

async function loadScanStatus() {
  try {
    const status = await (await fetch("/api/scan-status")).json();
    const label = status.stage === "complete" ? "Citywide cloud scan complete" : `Cloud ${status.stage} · ${status.screened}/${status.total}`;
    document.getElementById("live-pill-text").textContent = label;
  } catch (_) {}
}

document.getElementById("drawer-close").addEventListener("click", closeDrawer);
document.getElementById("drawer-backdrop").addEventListener("click", closeDrawer);
document.addEventListener("keydown", event => { if (event.key === "Escape") closeDrawer(); });
loadSnapshot().catch(error => { document.getElementById("case-list").innerHTML = `<div class="loading">${error.message}</div>`; });
loadScanStatus();
setInterval(loadScanStatus, 15000);
