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
const reasoningList = document.getElementById("reasoningList");
const hospitalList = document.getElementById("hospitalList");
const triageSource = document.getElementById("triageSource");
const submitButton = document.getElementById("submitButton");
const apiStatus = document.getElementById("apiStatus");
const locationStatus = document.getElementById("locationStatus");

function titleize(text) {
  return text.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    apiStatus.textContent = `${data.status.toUpperCase()} / ${data.database_mode}`;
  } catch (error) {
    apiStatus.textContent = "Offline";
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

  severityChip.textContent = triage.severity.toUpperCase();
  severityChip.className = `chip severity-${triage.severity}`;
  departmentValue.textContent = titleize(triage.department);
  hospitalValue.textContent = hospital ? hospital.name : "No match";
  etaValue.textContent = hospital ? `${hospital.eta_minutes} min` : "-";
  smsValue.textContent = data.sms.status.toUpperCase();
  triageSource.textContent = `Triage via ${triage.source}`;

  renderReasoning([
    ...triage.explanation,
    ...data.routing_reasoning,
    data.sms.error ? `SMS note: ${data.sms.error}` : `SMS body prepared`,
  ]);

  renderHospitals(data.candidate_hospitals);
  updateMap(hospital);
}

document.getElementById("triageForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  submitButton.textContent = "Routing...";

  const payload = {
    heart_rate: Number(document.getElementById("heartRate").value),
    systolic_bp: Number(document.getElementById("systolicBp").value),
    diastolic_bp: Number(document.getElementById("diastolicBp").value),
    oxygen_saturation: Number(document.getElementById("oxygen").value),
    injury: document.getElementById("injury").value.trim(),
    patient_lat: state.patientLat,
    patient_lon: state.patientLon,
  };

  try {
    const response = await fetch("/api/triage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    updateSummary(data);
  } catch (error) {
    renderReasoning([error.message || "Request failed"]);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Run Triage";
  }
});

checkHealth();
initLocation();
initMap();