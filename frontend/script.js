const state = {
  patientLat: 18.5204,
  patientLon: 73.8567,
  map: null,
  markers: [],
  routeLine: null,
  sessionId: crypto.randomUUID ? crypto.randomUUID() : `session-${Date.now()}`,
  currentScenario: "cardiac_arrest",
  selectedChips: [],
  liveVitals: {
    hr: 52,
    bp_sys: 90,
    bp_dia: 60,
    bp: "90/60",
    spo2: 91,
    rr: 22,
    timestamp: Date.now() / 1000,
  },
};

const healthState = {
  voiceReady: false,
  voiceDefaultConfigured: false,
};

const severityChip = document.getElementById("severityChip");
const severityHeadline = document.getElementById("severityHeadline");
const departmentValue = document.getElementById("departmentValue");
const hospitalValue = document.getElementById("hospitalValue");
const etaValue = document.getElementById("etaValue");
const smsValue = document.getElementById("smsValue");
const scoreValue = document.getElementById("scoreValue");
const reasoningList = document.getElementById("reasoningList");
const hospitalList = document.getElementById("hospitalList");
const triageSource = document.getElementById("triageSource");
const submitButton = document.getElementById("submitButton");
const callButton = document.getElementById("callButton");
const apiStatus = document.getElementById("apiStatus");
const locationStatus = document.getElementById("locationStatus");
const liveTime = document.getElementById("liveTime");
const dispatchRecommendation = document.getElementById("dispatchRecommendation");
const dispatchCard = document.getElementById("dispatchCard");
const reasoningBadge = document.getElementById("reasoningBadge");
const injuryField = document.getElementById("injury");
const voiceNumberInput = document.getElementById("voiceNumber");
const voiceHelp = document.getElementById("voiceHelp");
const triagePanel = document.querySelector(".triage-panel");
const dispatchPanel = document.querySelector(".dispatch-panel");
const scenarioButtons = Array.from(document.querySelectorAll(".scenario-button"));
const triageChips = Array.from(document.querySelectorAll(".triage-chip"));

const liveVitalsConfig = {
  hr: {
    valueEl: document.getElementById("liveHR"),
    barEl: document.getElementById("hrBar"),
    cardEl: document.getElementById("card-hr"),
    min: 30,
    max: 160,
  },
  spo2: {
    valueEl: document.getElementById("liveSPO2"),
    barEl: document.getElementById("spo2Bar"),
    cardEl: document.getElementById("card-spo2"),
    min: 70,
    max: 100,
  },
  bp: {
    valueEl: document.getElementById("liveBP"),
    barEl: document.getElementById("bpBar"),
    cardEl: document.getElementById("card-bp"),
    min: 70,
    max: 180,
  },
  rr: {
    valueEl: document.getElementById("liveRR"),
    barEl: document.getElementById("rrBar"),
    cardEl: document.getElementById("card-rr"),
    min: 5,
    max: 40,
  },
};

const scenarioPresets = {
  cardiac_arrest: {
    injury: "Witnessed collapse with pulseless episode, poor perfusion, and active resuscitation in progress.",
    chips: ["Chest Pain", "Unconscious"],
  },
  stroke: {
    injury: "Sudden facial droop, slurred speech, right-sided weakness, and last known well under 45 minutes.",
    chips: ["Stroke Signs"],
  },
  head_trauma: {
    injury: "Blunt head trauma after collision with worsening agitation, vomiting, and declining oxygenation.",
    chips: ["Head Injury", "Unconscious"],
  },
  respiratory_distress: {
    injury: "Severe respiratory distress with accessory muscle use, cyanosis, and rapidly dropping oxygen saturation.",
    chips: ["Respiratory Distress"],
  },
};

let currentSceneSeverity = "MEDIUM";

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function titleize(text) {
  return text.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatClock() {
  if (!liveTime) return;
  liveTime.textContent = new Intl.DateTimeFormat([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date());
}

function severityLabel(severity) {
  return severity ? severity.toUpperCase() : "STANDBY";
}

function severityBadgeClass(severity) {
  return `chip severity-${severity || "low"}`;
}

function severityBadgeMarkup(severity) {
  return `<span class="severity-dot"></span><span>${severityLabel(severity)}</span>`;
}

function resolveHospitalScore(hospital) {
  if (!hospital) return null;

  const numericDisplayScore = Number(hospital.display_score);
  if (Number.isFinite(numericDisplayScore) && numericDisplayScore > 0) return numericDisplayScore;

  const numericScore = Number(hospital.score);
  if (Number.isFinite(numericScore)) return numericScore <= 1 ? numericScore * 100 : numericScore;

  const numericRawScore = Number(hospital.raw_score);
  if (Number.isFinite(numericRawScore)) return 100 / (1 + Math.abs(numericRawScore));

  return null;
}

function scorePercent(score) {
  return Math.max(8, Math.min(100, Math.round(score || 0)));
}

function metricTone(value, type) {
  if (type === "eta") return value <= 12 ? "value-green" : value <= 20 ? "value-amber" : "value-red";
  if (type === "score") return value >= 80 ? "value-green" : value >= 60 ? "value-amber" : "value-red";
  if (type === "beds") return value >= 10 ? "value-green" : value >= 4 ? "value-amber" : "value-red";
  return value ? "value-green" : "value-red";
}

function scoreColor(score) {
  if (score >= 80) return "#22c55e";
  if (score >= 60) return "#f59e0b";
  return "#ef4444";
}

function badgeForSeverity(severity) {
  return `<span class="${severityBadgeClass(severity)}">${severityBadgeMarkup(severity)}</span>`;
}

function vitalTone(key, vitals) {
  if (key === "hr") {
    if (vitals.hr < 50 || vitals.hr > 130) return "alert";
    if (vitals.hr < 60 || vitals.hr > 110) return "warning";
    return "normal";
  }

  if (key === "spo2") {
    if (vitals.spo2 < 85) return "alert";
    if (vitals.spo2 < 92) return "warning";
    return "normal";
  }

  if (key === "bp") {
    if (vitals.bp_sys < 85 || vitals.bp_sys > 160) return "alert";
    if (vitals.bp_sys < 95 || vitals.bp_sys > 140) return "warning";
    return "normal";
  }

  if (vitals.rr > 30 || vitals.rr < 8) return "alert";
  if (vitals.rr > 24 || vitals.rr < 10) return "warning";
  return "normal";
}

function toneColor(tone) {
  if (tone === "alert") return "#ef4444";
  if (tone === "warning") return "#f59e0b";
  return "#22c55e";
}

function renderLiveVital(key, displayValue, scaleValue) {
  const config = liveVitalsConfig[key];
  if (!config?.valueEl || !config?.barEl || !config?.cardEl) return;

  const tone = vitalTone(key, state.liveVitals);
  const width = ((scaleValue - config.min) / (config.max - config.min)) * 100;

  config.valueEl.textContent = String(displayValue);
  config.valueEl.className = `vital-live-value ${tone}`;
  config.cardEl.className = tone === "normal" ? "vital-live-card" : `vital-live-card ${tone}`;
  config.barEl.style.width = `${clamp(width, 6, 100)}%`;
  config.barEl.style.backgroundColor = toneColor(tone);
}

function renderLiveVitals() {
  renderLiveVital("hr", Math.round(state.liveVitals.hr), state.liveVitals.hr);
  renderLiveVital("spo2", Math.round(state.liveVitals.spo2), state.liveVitals.spo2);
  renderLiveVital("bp", state.liveVitals.bp, state.liveVitals.bp_sys);
  renderLiveVital("rr", Math.round(state.liveVitals.rr), state.liveVitals.rr);
}

function renderReasoning(lines) {
  reasoningList.innerHTML = "";
  (lines || []).forEach((line) => {
    const item = document.createElement("li");
    item.textContent = line;
    reasoningList.appendChild(item);
  });
}

function buildDecisionReasoning(data) {
  const triage = data?.triage || {};
  const hospital = data?.selected_hospital || null;
  const vitals = state.liveVitals;
  const sceneCues = state.selectedChips.filter(Boolean);
  const reasoning = [];

  if (vitals && [vitals.hr, vitals.spo2, vitals.bp, vitals.rr].every((value) => value != null && value !== "")) {
    reasoning.push(`Vitals: HR ${vitals.hr} bpm, SpO2 ${vitals.spo2}%, BP ${vitals.bp}, RR ${vitals.rr}/min`);
  }

  reasoning.push(`Classified as ${String(triage.severity || "unknown").toUpperCase()} by rules-based triage engine`);

  if (sceneCues.length) {
    reasoning.push(`Scene flags: ${sceneCues.join(", ")}`);
  }

  if (triage.icu_required) {
    reasoning.push("ICU admission required");
  }
  if (triage.ventilator_required) {
    reasoning.push("Ventilator support indicated");
  }
  if (triage.specialist) {
    reasoning.push(`${titleize(triage.specialist)} specialist required`);
  }

  if (hospital?.name) {
    reasoning.push(`${hospital.name} selected - best match for ETA and specialization`);
  }

  return reasoning.filter((line) => {
    const normalized = String(line).toLowerCase();
    return (
      !normalized.includes("sms") &&
      !normalized.includes("twilio") &&
      !normalized.includes("voice call") &&
      !normalized.includes("not configured") &&
      !normalized.includes("not triggered")
    );
  });
}

function syncTopCardHeights() {
  if (!triagePanel || !dispatchPanel) return;
  triagePanel.style.height = "";
  dispatchPanel.style.height = "";
  if (window.innerWidth <= 980) return;

  const targetHeight = dispatchPanel.offsetHeight;
  if (targetHeight > 0) triagePanel.style.height = `${targetHeight}px`;
}

function setActiveControl(elements, predicate) {
  elements.forEach((element) => {
    element.classList.toggle("active", predicate(element));
  });
}

function syncScenarioButtons() {
  setActiveControl(scenarioButtons, (button) => button.dataset.scenario === state.currentScenario);
}

function syncChipButtons() {
  setActiveControl(triageChips, (chip) => state.selectedChips.includes(chip.dataset.chip));
}

function applyScenario(scenario) {
  const preset = scenarioPresets[scenario];
  if (!preset || !injuryField) return;

  state.currentScenario = scenario;
  state.selectedChips = [...preset.chips];
  injuryField.value = preset.injury;
  syncScenarioButtons();
  syncChipButtons();
  pollVitals();
}

function toggleChip(chip) {
  const value = chip.dataset.chip?.trim();
  if (!value) return;

  if (state.selectedChips.includes(value)) {
    state.selectedChips = state.selectedChips.filter((item) => item !== value);
  } else {
    state.selectedChips = [...state.selectedChips, value];
  }
  syncChipButtons();
}

function normalizePhoneNumber() {
  return voiceNumberInput?.value.trim() || "";
}

function isValidPhoneNumber(phoneNumber) {
  return /^\+[1-9]\d{7,14}$/.test(phoneNumber);
}

function updateVoiceHelp() {
  if (!voiceHelp) return;
  const manualNumber = normalizePhoneNumber();

  if (manualNumber) {
    voiceHelp.textContent = isValidPhoneNumber(manualNumber)
      ? `Call will be placed to ${manualNumber}.`
      : "Use E.164 format like +919876543210.";
    return;
  }

  if (healthState.voiceDefaultConfigured) {
    voiceHelp.textContent = "Leave the field empty to use the server default number, or type a number to override it.";
    return;
  }

  if (healthState.voiceReady) {
    voiceHelp.textContent = "Enter a number, then use the voice call button.";
    return;
  }

  voiceHelp.textContent = "Voice calling is unavailable until the server voice setup is configured.";
}

function updateCallButtonState() {
  const manualNumber = normalizePhoneNumber();
  const canUseManualNumber = manualNumber ? isValidPhoneNumber(manualNumber) : false;
  if (!callButton) return;
  callButton.disabled = !healthState.voiceReady || !(healthState.voiceDefaultConfigured || canUseManualNumber);
  updateVoiceHelp();
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();

    healthState.voiceReady = data.voice_ready === "true";
    healthState.voiceDefaultConfigured = data.voice_default_recipient_configured === "true";
    apiStatus.textContent = `${data.status.toUpperCase()} / ${data.database_mode} / ${data.voice_provider}`;

    if (!healthState.voiceReady) {
      if (callButton) callButton.disabled = true;
      updateVoiceHelp();
      return;
    }
    updateCallButtonState();
  } catch {
    apiStatus.textContent = "Offline";
    if (callButton) callButton.disabled = true;
    updateVoiceHelp();
  }
}

function initLocation() {
  if (!navigator.geolocation) {
    locationStatus.textContent = "Browser geolocation unavailable";
    return;
  }

  navigator.geolocation.getCurrentPosition(
    (position) => {
      state.patientLat = position.coords.latitude;
      state.patientLon = position.coords.longitude;
      locationStatus.textContent = `Live GPS ${state.patientLat.toFixed(4)}, ${state.patientLon.toFixed(4)}`;
      updateMap();
    },
    () => {
      locationStatus.textContent = "Using Pune fallback coordinates";
    },
    { enableHighAccuracy: true, timeout: 6000 }
  );
}

function initMap() {
  const mapElement = document.getElementById("map");
  if (!mapElement) return;

  if (!window.L) {
    mapElement.innerHTML = "<p>Leaflet could not load.</p>";
    return;
  }

  state.map = L.map("map").setView([state.patientLat, state.patientLon], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(state.map);

  updateMap();
}

function clearMapLayers() {
  state.markers.forEach((marker) => marker.remove());
  state.markers = [];

  if (state.routeLine) {
    state.map.removeControl(state.routeLine);
    state.routeLine = null;
  }
}

function updateMap(selectedHospital = null) {
  if (!state.map || !window.L) return;

  clearMapLayers();

  const patientMarker = L.marker([state.patientLat, state.patientLon])
    .addTo(state.map)
    .bindPopup("Ambulance / patient location");
  state.markers.push(patientMarker);

  if (selectedHospital) {
    const hospitalMarker = L.marker([selectedHospital.lat, selectedHospital.lon])
      .addTo(state.map)
      .bindPopup(selectedHospital.name);
    state.markers.push(hospitalMarker);

    state.routeLine = L.Routing.control({
      waypoints: [
        L.latLng(state.patientLat, state.patientLon),
        L.latLng(selectedHospital.lat, selectedHospital.lon),
      ],
      routeWhileDragging: false,
      addWaypoints: false,
      draggableWaypoints: false,
      fitSelectedRoutes: true,
      show: false,
      lineOptions: {
        styles: [{ color: "#f97316", opacity: 0.9, weight: 5 }],
      },
      createMarker(i, wp) {
        return L.marker(wp.latLng);
      },
    }).addTo(state.map);
    return;
  }

  state.map.setView([state.patientLat, state.patientLon], 12);
}

function renderHospitals(hospitals) {
  hospitalList.innerHTML = "";

  const recommendedHospitalName = hospitalValue?.textContent?.trim().toLowerCase() || "";
  const alternativeHospitals = (hospitals || []).filter((hospital) => {
    return hospital?.name?.trim().toLowerCase() !== recommendedHospitalName;
  });

  alternativeHospitals.slice(0, 5).forEach((hospital, index) => {
    const displayScore = resolveHospitalScore(hospital) ?? 0;
    const card = document.createElement("article");
    const progress = scorePercent(displayScore);
    const tone = scoreColor(displayScore);
    const departmentText = titleize((hospital.departments || []).join(", "));
    const icuText = hospital.icu_available ? "ICU available" : "No ICU";
    const bedText = `${hospital.available_beds} beds open`;
    const rank = index + 2;

    card.className = "candidate-card";
    card.innerHTML = `
      <div class="candidate-top">
        <div class="candidate-title">
          <strong>${hospital.name}</strong>
          <p class="candidate-subtitle">${hospital.eta_minutes} min ETA</p>
        </div>
        <span class="badge">${rank}</span>
      </div>
      <div class="candidate-metrics">
        <div class="metric-row">
          <span class="metric-chip">${departmentText || "General access"}</span>
          <span class="metric-chip">${bedText}</span>
          <span class="metric-chip">${icuText}</span>
        </div>
        <span class="${metricTone(displayScore, "score")}">${displayScore.toFixed(1)}%</span>
      </div>
      <div class="progress-wrap">
        <div class="progress-meta">
          <span>Match Confidence</span>
          <span>${progress}%</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" style="width: ${progress}%; background: linear-gradient(90deg, ${tone}66, ${tone});"></div>
        </div>
      </div>
      <p class="candidate-departments">${departmentText}</p>
      <p class="candidate-reason">${hospital.routing_reason}</p>
    `;
    hospitalList.appendChild(card);
  });
}

function updateSummary(data) {
  const triage = data.triage;
  const hospital = data.selected_hospital;
  const severity = triage.severity;
  const hospitalScore = resolveHospitalScore(hospital);
  const hospitalBeds = hospital?.available_beds ?? null;

  severityChip.innerHTML = severityBadgeMarkup(severity);
  severityChip.className = severityBadgeClass(severity);
  severityHeadline.textContent = severityLabel(severity);
  departmentValue.textContent = titleize(triage.department || "-");
  departmentValue.className = "";
  hospitalValue.textContent = hospital ? hospital.name : "No match";
  etaValue.textContent = hospital ? `${hospital.eta_minutes} min` : "-";
  etaValue.className = hospital ? metricTone(hospital.eta_minutes, "eta") : "";
  smsValue.textContent = hospitalBeds != null ? `${hospitalBeds}` : "-";
  smsValue.className = hospitalBeds != null ? metricTone(hospitalBeds, "beds") : "";
  scoreValue.textContent = hospitalScore != null ? `${hospitalScore.toFixed(1)}%` : "-";
  scoreValue.className = hospitalScore != null ? metricTone(hospitalScore, "score") : "";
  triageSource.textContent = `Triage via ${triage.source}`;
  dispatchRecommendation.innerHTML = `
    <span class="status-key">Status</span>
    <strong>${hospital ? "Destination locked" : "No match"}</strong>
  `;
  dispatchCard.classList.toggle("selected", Boolean(hospital));
  document.getElementById("recommendedBadge").outerHTML = hospital
    ? '<span class="badge badge-recommended" id="recommendedBadge">Recommended</span>'
    : '<span class="badge" id="recommendedBadge">Pending</span>';
  reasoningBadge.innerHTML = badgeForSeverity(severity);

  renderReasoning(buildDecisionReasoning(data));

  renderHospitals(data.candidate_hospitals);
  updateMap(hospital);
  syncTopCardHeights();
}

function buildPayload(includeVoiceNumber = false) {
  const payload = {
    hr: state.liveVitals.hr,
    bp_sys: state.liveVitals.bp_sys,
    bp_dia: state.liveVitals.bp_dia,
    spo2: state.liveVitals.spo2,
    rr: state.liveVitals.rr,
    scenario: state.currentScenario,
    chips: state.selectedChips,
    injury: injuryField.value.trim(),
    patient_lat: state.patientLat,
    patient_lon: state.patientLon,
    scene_severity: currentSceneSeverity,
  };

  if (includeVoiceNumber) {
    const manualNumber = normalizePhoneNumber();
    if (manualNumber) payload.recipient_phone_number = manualNumber;
  }

  return payload;
}

async function runWorkflow(endpoint, button, busyText, idleText, includeVoiceNumber = false) {
  if (endpoint === "/api/voice/test-call" && !healthState.voiceReady) {
    renderReasoning(["Voice call not started: the server voice integration is not configured."]);
    return;
  }

  const manualNumber = normalizePhoneNumber();
  if (endpoint === "/api/voice/test-call" && manualNumber && !isValidPhoneNumber(manualNumber)) {
    renderReasoning(["Voice call not started: enter the phone number in E.164 format, for example +919876543210."]);
    return;
  }

  if (endpoint === "/api/voice/test-call" && !manualNumber && !healthState.voiceDefaultConfigured) {
    renderReasoning(["Voice call not started: enter a phone number first."]);
    return;
  }

  submitButton.disabled = true;
  if (callButton) callButton.disabled = true;
  button.textContent = busyText;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 25000);

    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload(includeVoiceNumber)),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Request failed");
    updateSummary(data);
  } catch (error) {
    if (error.name === "AbortError") {
      renderReasoning(["Request timed out. The server took too long to respond, so the UI was unlocked."]);
    } else {
      renderReasoning([error.message || "Request failed"]);
    }
  } finally {
    submitButton.disabled = false;
    updateCallButtonState();
    submitButton.textContent = "Run Triage";
    if (callButton) callButton.textContent = "Call";
    button.textContent = idleText;
  }
}

async function pollVitals() {
  try {
    const response = await fetch(`/api/vitals/${state.sessionId}/${state.currentScenario}`);
    const vitals = await response.json();
    if (!response.ok) throw new Error(vitals.detail || "Vitals feed unavailable");
    state.liveVitals = vitals;
    renderLiveVitals();
  } catch (error) {
    renderReasoning([error.message || "Vitals feed unavailable"]);
  }
}

document.getElementById("triageForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await runWorkflow("/api/triage", submitButton, "Routing...", "Run Triage");
});

callButton?.addEventListener("click", async () => {
  await runWorkflow("/api/voice/test-call", callButton, "Calling...", "Call", true);
});

scenarioButtons.forEach((button) => {
  button.addEventListener("click", () => applyScenario(button.dataset.scenario));
});

triageChips.forEach((chip) => {
  chip.addEventListener("click", () => toggleChip(chip));
});

voiceNumberInput?.addEventListener("input", updateCallButtonState);

document.getElementById("analyze-btn")?.addEventListener("click", async () => {
  const fileInput = document.getElementById("scene-photo");
  const banner = document.getElementById("severity-banner");

  if (!fileInput.files[0]) {
    alert("Please capture a photo first.");
    return;
  }

  const formData = new FormData();
  formData.append("image", fileInput.files[0]);

  try {
    const response = await fetch("/analyze-scene", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    currentSceneSeverity = data.severity;

    banner.classList.remove("hidden", "bg-red", "bg-yellow", "bg-green");
    if (data.severity === "HIGH") {
      banner.innerText = "HIGH SEVERITY SCENE - Routing to Level 1 Trauma Centers only";
      banner.classList.add("bg-red");
    } else if (data.severity === "MEDIUM") {
      banner.innerText = "MEDIUM SEVERITY SCENE - Standard routing active";
      banner.classList.add("bg-yellow");
    } else {
      banner.innerText = "LOW SEVERITY SCENE - Standard routing active";
      banner.classList.add("bg-green");
    }
  } catch (error) {
    console.error("Analysis failed", error);
    alert("Scene analysis failed. Using standard routing.");
  }
});

formatClock();
renderLiveVitals();
syncScenarioButtons();
syncChipButtons();
setInterval(formatClock, 1000);
setInterval(pollVitals, 1400);
updateVoiceHelp();
checkHealth();
initLocation();
initMap();
syncTopCardHeights();
window.addEventListener("resize", syncTopCardHeights);
applyScenario(state.currentScenario);
