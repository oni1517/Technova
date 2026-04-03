const state = {
  patientLat: 18.5204,
  patientLon: 73.8567,
  map: null,
  markers: [],
  routeLine: null,
};

const severityChip = document.getElementById("severityChip");
const departmentValue = document.getElementById("departmentValue");
const hospitalValue = document.getElementById("hospitalValue");
const etaValue = document.getElementById("etaValue");
const smsValue = document.getElementById("smsValue");
const voiceValue = document.getElementById("voiceValue");
const reasoningList = document.getElementById("reasoningList");
const hospitalList = document.getElementById("hospitalList");
const triageSource = document.getElementById("triageSource");
const submitButton = document.getElementById("submitButton");
const callButton = document.getElementById("callButton");
const apiStatus = document.getElementById("apiStatus");
const locationStatus = document.getElementById("locationStatus");
const voiceNumberInput = document.getElementById("voiceNumber");
const voiceHelp = document.getElementById("voiceHelp");

const healthState = {
  voiceReady: false,
  voiceDefaultConfigured: false,
  voiceDefaultMasked: "",
};

function titleize(text) {
  return text.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    healthState.voiceReady = data.voice_ready === "true";
    healthState.voiceDefaultConfigured = data.voice_default_recipient_configured === "true";
    healthState.voiceDefaultMasked = data.voice_default_recipient_masked || "";

    apiStatus.textContent = `${data.status.toUpperCase()} / ${data.database_mode} / ${data.voice_provider}`;

    if (!healthState.voiceReady) {
      voiceHelp.textContent = "Voice call setup is incomplete on the server. Check Bolna API key and agent ID.";
      callButton.disabled = true;
      return;
    }

    if (healthState.voiceDefaultConfigured) {
      voiceHelp.textContent = `Leave the field empty to use the configured default number ${healthState.voiceDefaultMasked}.`;
    } else {
      voiceHelp.textContent = "Enter a verified E.164 number to place a voice call.";
    }
  } catch (error) {
    apiStatus.textContent = "Offline";
    voiceHelp.textContent = "API is offline, so voice calling is unavailable.";
    callButton.disabled = true;
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
  if (!window.L) {
    document.getElementById("map").innerHTML = "<p>Leaflet could not load.</p>";
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
        L.latLng(selectedHospital.lat, selectedHospital.lon)
      ],
      routeWhileDragging: false,
      addWaypoints: false,
      draggableWaypoints: false,
      fitSelectedRoutes: true,
      show: false,
      lineOptions: {
        styles: [{ color: "#f97316", opacity: 0.9, weight: 5 }]
      },
      createMarker: function(i, wp) {
        return L.marker(wp.latLng);
      }
    }).addTo(state.map);

    return;
  }

  state.map.setView([state.patientLat, state.patientLon], 12);
}

function renderReasoning(lines) {
  reasoningList.innerHTML = "";
  (lines || []).forEach((line) => {
    const item = document.createElement("li");
    item.textContent = line;
    reasoningList.appendChild(item);
  });
}

// ⭐ UPDATED FUNCTION (TOP 5 HOSPITALS)
function renderHospitals(hospitals) {
  hospitalList.innerHTML = "";

  (hospitals || []).slice(0, 5).forEach((hospital, index) => {
    const card = document.createElement("article");
    card.className = "candidate-card";
    card.innerHTML = `
      <div class="candidate-top">
        <strong>#${index + 1} ${hospital.name}</strong>
        <span>${hospital.eta_minutes} min</span>
      </div>
      <p>${titleize(hospital.departments.join(", "))}</p>
      <p>Score ${hospital.score.toFixed(3)} | Beds ${hospital.available_beds} | ICU ${hospital.icu_available ? "Yes" : "No"}</p>
      <p>${hospital.routing_reason}</p>
    `;
    hospitalList.appendChild(card);
  });
}

function updateSummary(data) {
  const triage = data.triage;
  const hospital = data.selected_hospital;
  const voiceCall = data.voice_call;

  severityChip.textContent = triage.severity.toUpperCase();
  severityChip.className = `chip severity-${triage.severity}`;
  departmentValue.textContent = titleize(triage.department);
  hospitalValue.textContent = hospital ? hospital.name : "No match";
  etaValue.textContent = hospital ? `${hospital.eta_minutes} min` : "-";
  smsValue.textContent = data.sms.status.toUpperCase();
  voiceValue.textContent = voiceCall ? voiceCall.status.toUpperCase() : "NOT RUN";
  triageSource.textContent = `Triage via ${triage.source}`;

  renderReasoning([
    ...triage.explanation,
    ...data.routing_reasoning,
    data.sms.error ? `SMS note: ${data.sms.error}` : `SMS body prepared`,
    voiceCall
      ? (
        voiceCall.error
          ? `Voice call note: ${voiceCall.error}`
          : `Voice call ${voiceCall.status} via ${voiceCall.provider}${voiceCall.execution_id ? ` (${voiceCall.execution_id})` : ""}`
      )
      : "Voice call not triggered",
  ]);

  renderHospitals(data.candidate_hospitals);
  updateMap(hospital);
}

function buildPayload(includeVoiceNumber = false) {
  const payload = {
    heart_rate: Number(document.getElementById("heartRate").value),
    systolic_bp: Number(document.getElementById("systolicBp").value),
    diastolic_bp: Number(document.getElementById("diastolicBp").value),
    oxygen_saturation: Number(document.getElementById("oxygen").value),
    injury: document.getElementById("injury").value.trim(),
    patient_lat: state.patientLat,
    patient_lon: state.patientLon,
  };

  if (includeVoiceNumber) {
    const voiceNumber = document.getElementById("voiceNumber").value.trim();
    if (voiceNumber) {
      payload.recipient_phone_number = voiceNumber;
    }
  }

  return payload;
}

async function runWorkflow(endpoint, button, busyText, idleText, includeVoiceNumber = false) {
  if (
    endpoint === "/api/voice/test-call" &&
    !voiceNumberInput.value.trim() &&
    !healthState.voiceDefaultConfigured
  ) {
    renderReasoning(["Voice call not started: no recipient number was entered and no default test number is configured."]);
    voiceValue.textContent = "SKIPPED";
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
    callButton.disabled = false;
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

checkHealth();
initLocation();
initMap();
