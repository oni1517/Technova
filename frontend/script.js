const state = {
  patientLat: 18.5204,
  patientLon: 73.8567,
  map: null,
  markers: [],
  routeLine: null,
  liveVitals: {
    heart_rate: 132,
    systolic_bp: 92,
    diastolic_bp: 58,
    oxygen_saturation: 89,
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
  heart_rate: {
    valueEl: document.getElementById("liveHR"),
    barEl: document.getElementById("hrBar"),
    cardEl: document.getElementById("card-hr"),
    min: 40,
    max: 180,
  },
  oxygen_saturation: {
    valueEl: document.getElementById("liveSPO2"),
    barEl: document.getElementById("spo2Bar"),
    cardEl: document.getElementById("card-spo2"),
    min: 70,
    max: 100,
  },
  systolic_bp: {
    valueEl: document.getElementById("liveSYS"),
    barEl: document.getElementById("sysBar"),
    cardEl: document.getElementById("card-sys"),
    min: 70,
    max: 180,
  },
  diastolic_bp: {
    valueEl: document.getElementById("liveDIA"),
    barEl: document.getElementById("diaBar"),
    cardEl: document.getElementById("card-dia"),
    min: 40,
    max: 120,
  },
};

const scenarioPresets = {
  "chest-trauma": {
    injury: "Road traffic accident with chest trauma, heavy bleeding, and suspected rib fractures.",
    vitals: { heart_rate: 132, systolic_bp: 88, diastolic_bp: 58, oxygen_saturation: 89 },
  },
  "stroke-alert": {
    injury: "Sudden facial droop, slurred speech, right-sided weakness, and last known well under 45 minutes.",
    vitals: { heart_rate: 104, systolic_bp: 168, diastolic_bp: 102, oxygen_saturation: 95 },
  },
  burns: {
    injury: "Industrial burn exposure with partial-thickness burns to torso and arms, severe pain, and smoke inhalation risk.",
    vitals: { heart_rate: 126, systolic_bp: 96, diastolic_bp: 62, oxygen_saturation: 91 },
  },
  pediatric: {
    injury: "Pediatric fall with altered responsiveness, possible head injury, repeated vomiting, and anxious guardian on scene.",
    vitals: { heart_rate: 138, systolic_bp: 92, diastolic_bp: 60, oxygen_saturation: 94 },
  },
};

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function randomStep(size) {
  return Math.round((Math.random() * size * 2 - size) * 10) / 10;
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
  if (Number.isFinite(numericDisplayScore) && numericDisplayScore > 0) {
    return numericDisplayScore;
  }

  const numericScore = Number(hospital.score);
  if (Number.isFinite(numericScore)) {
    return numericScore <= 1 ? numericScore * 100 : numericScore;
  }

  const numericRawScore = Number(hospital.raw_score);
  if (Number.isFinite(numericRawScore)) {
    return 100 / (1 + Math.abs(numericRawScore));
  }

  return null;
}

function scorePercent(score) {
  return Math.max(8, Math.min(100, Math.round(score || 0)));
}

function metricTone(value, type) {
  if (type === "eta") {
    return value <= 12 ? "value-green" : value <= 20 ? "value-amber" : "value-red";
  }

  if (type === "score") {
    return value >= 80 ? "value-green" : value >= 60 ? "value-amber" : "value-red";
  }

  if (type === "beds") {
    return value >= 10 ? "value-green" : value >= 4 ? "value-amber" : "value-red";
  }

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

function vitalTone(key, value) {
  if (key === "heart_rate") {
    if (value >= 130 || value <= 45) return "alert";
    if (value >= 110 || value <= 55) return "warning";
    return "normal";
  }

  if (key === "oxygen_saturation") {
    if (value <= 88) return "alert";
    if (value <= 93) return "warning";
    return "normal";
  }

  if (key === "systolic_bp") {
    if (value <= 85 || value >= 165) return "alert";
    if (value <= 95 || value >= 145) return "warning";
    return "normal";
  }

  if (value <= 50 || value >= 105) return "alert";
  if (value <= 60 || value >= 95) return "warning";
  return "normal";
}

function toneColor(tone) {
  if (tone === "alert") return "#ef4444";
  if (tone === "warning") return "#f59e0b";
  return "#22c55e";
}

function renderLiveVital(key, value) {
  const config = liveVitalsConfig[key];
  if (!config?.valueEl || !config?.barEl || !config?.cardEl) return;

  const tone = vitalTone(key, value);
  const width = ((value - config.min) / (config.max - config.min)) * 100;

  config.valueEl.textContent = String(Math.round(value));
  config.valueEl.className = `vital-live-value ${tone}`;
  config.cardEl.className = tone === "normal" ? "vital-live-card" : `vital-live-card ${tone}`;
  config.barEl.style.width = `${clamp(width, 6, 100)}%`;
  config.barEl.style.backgroundColor = toneColor(tone);
}

function renderLiveVitals() {
  Object.entries(state.liveVitals).forEach(([key, value]) => {
    renderLiveVital(key, value);
  });
}

function tickLiveVitals() {
  const nextHeartRate = clamp(
    state.liveVitals.heart_rate + randomStep(6) + (Math.random() < 0.18 ? randomStep(10) : 0),
    82,
    152
  );
  const nextSpo2 = clamp(
    state.liveVitals.oxygen_saturation + randomStep(1.4) + (Math.random() < 0.12 ? -1 : 0),
    84,
    99
  );
  const nextSystolic = clamp(
    state.liveVitals.systolic_bp + randomStep(4) + (Math.random() < 0.16 ? randomStep(7) : 0),
    82,
    132
  );
  const nextDiastolic = clamp(state.liveVitals.diastolic_bp + randomStep(3), 48, 86);

  state.liveVitals = {
    heart_rate: Math.round(nextHeartRate),
    systolic_bp: Math.max(Math.round(nextSystolic), Math.round(nextDiastolic) + 18),
    diastolic_bp: Math.round(nextDiastolic),
    oxygen_saturation: Math.round(nextSpo2),
  };

  renderLiveVitals();
}

function renderReasoning(lines) {
  reasoningList.innerHTML = "";

  (lines || []).forEach((line) => {
    const item = document.createElement("li");
    item.textContent = line;
    reasoningList.appendChild(item);
  });
}

function syncTopCardHeights() {
  if (!triagePanel || !dispatchPanel) return;

  triagePanel.style.height = "";
  dispatchPanel.style.height = "";

  if (window.innerWidth <= 980) return;

  const targetHeight = dispatchPanel.offsetHeight;
  if (targetHeight > 0) {
    triagePanel.style.height = `${targetHeight}px`;
  }
}

function setActiveControl(elements, activeElement, allowToggleOff = false) {
  elements.forEach((element) => {
    const shouldActivate = element === activeElement && !(allowToggleOff && element.classList.contains("active"));
    element.classList.toggle("active", shouldActivate);
  });
}

function applyScenario(key, button) {
  const preset = scenarioPresets[key];
  if (!preset || !injuryField) return;

  injuryField.value = preset.injury;
  state.liveVitals = { ...preset.vitals };
  renderLiveVitals();
  setActiveControl(scenarioButtons, button);
}

function appendTriageChip(chip) {
  if (!injuryField) return;

  const note = chip.dataset.chip?.trim();
  if (!note) return;

  const normalizedValue = injuryField.value.trim().toLowerCase();
  if (!normalizedValue.includes(note.toLowerCase())) {
    const separator = normalizedValue ? (/[.!?]$/.test(injuryField.value.trim()) ? " " : "; ") : "";
    injuryField.value = `${injuryField.value.trim()}${separator}${note}`.trim();
  }

  chip.classList.add("active");
  window.setTimeout(() => chip.classList.remove("active"), 900);
}

function normalizePhoneNumber() {
  return voiceNumberInput?.value.trim() || "";
}

function hasManualVoiceNumber() {
  return Boolean(normalizePhoneNumber());
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
      callButton.disabled = true;
      updateVoiceHelp();
      return;
    }
    updateCallButtonState();
  } catch (error) {
    apiStatus.textContent = "Offline";
    callButton.disabled = true;
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
      createMarker: function (i, wp) {
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
  const voiceCall = data.voice_call;

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

  renderReasoning([
    ...triage.explanation,
    ...data.routing_reasoning,
    data.sms?.error ? `SMS: ${data.sms.error}` : `SMS: ${data.sms?.status || "not run"}.`,
    voiceCall
      ? (
        voiceCall.error
          ? `Voice call: ${voiceCall.error}`
          : `Voice call: ${voiceCall.status} via ${voiceCall.provider}${voiceCall.execution_id ? ` (${voiceCall.execution_id})` : ""}.`
      )
      : "Voice call: not triggered.",
  ]);

  renderHospitals(data.candidate_hospitals);
  updateMap(hospital);
  syncTopCardHeights();
}

function buildPayload(includeVoiceNumber = false) {
  const payload = {
    heart_rate: state.liveVitals.heart_rate,
    systolic_bp: state.liveVitals.systolic_bp,
    diastolic_bp: state.liveVitals.diastolic_bp,
    oxygen_saturation: state.liveVitals.oxygen_saturation,
    injury: injuryField.value.trim(),
    patient_lat: state.patientLat,
    patient_lon: state.patientLon,
  };

  if (includeVoiceNumber) {
    const manualNumber = normalizePhoneNumber();
    if (manualNumber) {
      payload.recipient_phone_number = manualNumber;
    }
    return payload;
  }

  return payload;
}

async function runWorkflow(endpoint, button, busyText, idleText, includeVoiceNumber = false) {
  if (endpoint === "/api/voice/test-call" && !healthState.voiceReady) {
    renderReasoning([
      "Voice call not started: the server voice integration is not configured.",
    ]);
    return;
  }

  const manualNumber = normalizePhoneNumber();
  if (endpoint === "/api/voice/test-call" && manualNumber && !isValidPhoneNumber(manualNumber)) {
    renderReasoning([
      "Voice call not started: enter the phone number in E.164 format, for example +919876543210.",
    ]);
    return;
  }

  if (endpoint === "/api/voice/test-call" && !manualNumber && !healthState.voiceDefaultConfigured) {
    renderReasoning([
      "Voice call not started: enter a phone number first.",
    ]);
    return;
  }

  submitButton.disabled = true;
  callButton.disabled = true;
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

    if (!response.ok) {
      throw new Error(data.detail || "Request failed");
    }

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
    callButton.textContent = "Run Triage + Voice Call";
    button.textContent = idleText;
  }
}

document.getElementById("triageForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await runWorkflow("/api/triage", submitButton, "Routing...", "Run Triage");
});

callButton.addEventListener("click", async () => {
  await runWorkflow(
    "/api/voice/test-call",
    callButton,
    "Routing + Calling...",
    "Run Triage + Voice Call",
    true
  );
});

scenarioButtons.forEach((button) => {
  button.addEventListener("click", () => applyScenario(button.dataset.scenario, button));
});

triageChips.forEach((chip) => {
  chip.addEventListener("click", () => appendTriageChip(chip));
});

voiceNumberInput?.addEventListener("input", updateCallButtonState);

formatClock();
renderLiveVitals();
setInterval(tickLiveVitals, 1400);
setInterval(formatClock, 1000);
updateVoiceHelp();
checkHealth();
initLocation();
initMap();
syncTopCardHeights();
window.addEventListener("resize", syncTopCardHeights);
