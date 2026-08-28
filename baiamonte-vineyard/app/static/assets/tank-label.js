const esc = (value) => String(value ?? "—").replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const value = (raw, suffix = "") => raw === null || raw === undefined || raw === "" ? "—" : `${esc(raw)}${suffix}`;
const number = (raw, digits = 1) => {
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return "—";
  return new Intl.NumberFormat("it-IT", {maximumFractionDigits: digits}).format(parsed);
};
const vesselType = (type, stage) => {
  const physical = String(type || "").toLowerCase();
  const combined = `${physical} ${stage || ""}`.toLowerCase();
  if (/demijohn|demijon|damigiana|carboy/.test(physical)) return "demijohn";
  if (/barrel|barrique|tonneau|oak/.test(physical)) return "barrel";
  if (/amphora|anfora|clay/.test(physical)) return "amphora";
  if (/press|receiv/.test(physical)) return "press";
  if (/bin|crate|harvest/.test(physical)) return "bin";
  if (/ferment/.test(physical)) return "fermenter";
  if (/age|aging|maturation/.test(physical)) return "aging";
  if (/other|custom|unknown/.test(physical)) return "other";
  if (physical) return "tank";
  if (/press/.test(combined)) return "press";
  if (/ferment|macer|must/.test(combined)) return "fermenter";
  if (/age|aging|maturation|settling/.test(combined)) return "aging";
  return "tank";
};
const cellarStageClass = (stage) => {
  const text = String(stage || "").toLowerCase();
  if (/ferment|macerat/.test(text)) return "fermenting";
  if (/age|aging|matur|elevage/.test(text)) return "aging";
  if (/sett|clarif|rack|stabil/.test(text)) return "settling";
  if (/transfer|press|pump|fill|drain/.test(text)) return "transfer";
  return "resting";
};
const sparkline = (rows, key, label, suffix = "") => {
  const points = (rows || []).map((row) => row[key]).filter((raw) => raw !== null && raw !== undefined && raw !== "").map(Number).filter(Number.isFinite);
  const latest = points.length ? points.at(-1) : null;
  if (points.length < 2) return `<div class="micro-chart waiting"><small>${label}</small><b>${latest === null ? "—" : `${number(latest, 3)}${suffix}`}</b><span>Storico in attesa</span></div>`;
  const min = Math.min(...points), max = Math.max(...points), spread = max - min || 1;
  const path = points.map((point, index) => `${(index / (points.length - 1) * 100).toFixed(1)},${(31 - ((point - min) / spread * 25)).toFixed(1)}`).join(" ");
  return `<div class="micro-chart"><small>${label}</small><b>${number(latest, 3)}${suffix}</b><svg viewBox="0 0 100 36" preserveAspectRatio="none" role="img" aria-label="Andamento ${label}"><defs><linearGradient id="spark-${key}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e0b92f" stop-opacity=".35"/><stop offset="1" stop-color="#e0b92f" stop-opacity="0"/></linearGradient></defs><polygon points="0,36 ${path} 100,36" fill="url(#spark-${key})"/><polyline points="${path}" fill="none" stroke="#e0b92f" stroke-width="2" vector-effect="non-scaling-stroke"/></svg><span>${points.length} letture</span></div>`;
};
let latestTankData = null;
let tankSensorTimer = null;
let tankSensorPinned = false;
let tankSensorDeadline = 0;

const tankSensorChart = (rows, key, label, unit, target = null) => {
  const data = (rows || []).map((row) => ({time: row.time, value: Number(row[key])})).filter((row) => row.time && Number.isFinite(row.value));
  if (data.length < 2) return `<div class="tank-sensor-chart waiting"><b>${esc(label)}</b><span>Storico in attesa</span></div>`;
  const values = data.map((row) => row.value);
  const targetValue = target === null || target === undefined || target === "" ? Number.NaN : Number(target);
  if (Number.isFinite(targetValue)) values.push(targetValue);
  let min = Math.min(...values), max = Math.max(...values);
  const padding = (max - min || .01) * .14;
  min -= padding; max += padding;
  const x = (index) => 24 + index / (data.length - 1) * 552;
  const y = (reading) => 142 - (reading - min) / (max - min) * 112;
  const points = data.map((row, index) => `${x(index).toFixed(1)},${y(row.value).toFixed(1)}`).join(" ");
  const latest = data.at(-1);
  return `<figure class="tank-sensor-chart"><figcaption><b>${esc(label)}</b><span>${number(latest.value, 3)}${esc(unit)}</span></figcaption><svg viewBox="0 0 600 160" role="img" aria-label="${esc(label)} storico Tank Sensor"><line x1="24" y1="30" x2="576" y2="30"/><line x1="24" y1="86" x2="576" y2="86"/><line x1="24" y1="142" x2="576" y2="142"/>${Number.isFinite(targetValue) ? `<line class="target" x1="24" y1="${y(targetValue).toFixed(1)}" x2="576" y2="${y(targetValue).toFixed(1)}"/><text x="570" y="${Math.max(12, y(targetValue) - 5).toFixed(1)}" text-anchor="end">obiettivo ${number(targetValue, 3)}</text>` : ""}<polyline points="${points}"/><circle cx="${x(data.length - 1).toFixed(1)}" cy="${y(latest.value).toFixed(1)}" r="4"/><text x="24" y="157">${new Date(data[0].time).toLocaleDateString("it-IT")}</text><text x="576" y="157" text-anchor="end">adesso</text></svg></figure>`;
};

const tankSensorHistory = (history) => {
  const rows = history?.vintages || [];
  if (!rows.length) return `<div class="tank-sensor-history empty"><b>Storico annata e vitigno</b><span>Nessun dato storico collegato al vitigno registrato.</span></div>`;
  return `<div class="tank-sensor-history"><b>Storico annata e vitigno</b><div>${rows.slice(0, 8).map((row) => `<span><strong>${value(row.vintage_year)}</strong><em>${value(row.variety_name)}</em><small>${row.grapes_kg == null ? "uva —" : `${number(row.grapes_kg, 0)} kg uva`} · ${row.wine_l == null ? "vino —" : `${number(row.wine_l, 0)} L vino`}</small></span>`).join("")}</div></div>`;
};

const ensureTankSensorOverlay = () => {
  let overlay = document.getElementById("tankSensorOverlay");
  if (overlay) return overlay;
  overlay = document.createElement("section");
  overlay.id = "tankSensorOverlay";
  overlay.className = "tank-sensor-overlay";
  overlay.hidden = true;
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", "tankSensorHeading");
  overlay.innerHTML = `<header><div><small>ENOLOGY · TANK SENSOR</small><h2 id="tankSensorHeading">Tank Sensor process</h2><p id="tankSensorMeta"></p></div><div class="tank-sensor-controls"><span id="tankSensorMode"></span><button type="button" id="tankSensorClose">Chiudi</button></div></header><div id="tankSensorBody" class="tank-sensor-body"></div>`;
  document.body.appendChild(overlay);
  overlay.querySelector("#tankSensorClose").addEventListener("click", closeTankSensor);
  return overlay;
};

function closeTankSensor() {
  clearTimeout(tankSensorTimer);
  tankSensorTimer = null;
  tankSensorPinned = false;
  tankSensorDeadline = 0;
  const overlay = document.getElementById("tankSensorOverlay");
  if (overlay) overlay.hidden = true;
  document.body.classList.remove("tank-sensor-open");
  document.getElementById("liveDot")?.setAttribute("aria-expanded", "false");
}

const updateTankSensorCountdown = () => {
  const mode = document.getElementById("tankSensorMode");
  if (!mode || tankSensorPinned) return;
  const seconds = Math.max(0, Math.ceil((tankSensorDeadline - Date.now()) / 1000));
  mode.textContent = `Si chiude tra ${seconds}s · tocca di nuovo la luce per fissare`;
  if (seconds > 0) setTimeout(updateTankSensorCountdown, 250);
};

const renderTankSensorOverlay = (d) => {
  const overlay = ensureTankSensorOverlay();
  const sensor = d?.plaato || null;
  const projection = sensor?.projection || {};
  const grapeTypes = d?.wine_history?.grape_types || [];
  overlay.querySelector("#tankSensorHeading").textContent = `${d?.code || "Serbatoio"} · ${d?.name || "Tank Sensor"}`;
  overlay.querySelector("#tankSensorMeta").textContent = `Annata ${d?.vintage_year || "—"} · Vitigno ${grapeTypes.join(" / ") || d?.variety_summary || "—"} · ${d?.wine_lot_code || "lotto non registrato"}`;
  const body = overlay.querySelector("#tankSensorBody");
  if (!sensor) {
    body.innerHTML = `<div class="tank-sensor-unavailable"><h3>Tank Sensor non collegato</h3><p>I dati legali del serbatoio restano visibili. Configurare il sensore automatico per mostrare fermentazione e grafici.</p></div>${tankSensorHistory(d?.wine_history)}`;
    return;
  }
  const finish = projection.estimated_finish_at ? new Date(projection.estimated_finish_at).toLocaleString("it-IT") : "In attesa di andamento stabile";
  body.innerHTML = `<div class="tank-sensor-kpis"><span><small>Temperatura</small><b>${value(sensor.temperature_c, "°C")}</b></span><span><small>Densità</small><b>${value(sensor.density_sg, " SG")}</b></span><span><small>Attività</small><b>${value(sensor.fermentation_rate_msg_h, " mSG/h")}</b></span><span><small>Alcol stimato</small><b>${value(projection.current_abv_estimate_pct, "%")}</b></span><span><small>Avanzamento</small><b>${value(projection.progress_pct, "%")}</b></span><span><small>Fine stimata</small><b>${esc(finish)}</b></span></div><div class="tank-sensor-charts">${tankSensorChart(sensor.history, "density_sg", "Densità", " SG", sensor.final_gravity)}${tankSensorChart(sensor.history, "temperature_c", "Temperatura", "°C")}</div><div class="tank-sensor-foot"><span><small>Fase calcolata</small><b>${value(projection.phase)}</b></span><span><small>Affidabilità</small><b>${value(projection.confidence)}</b></span><span><small>Salute Tank Sensor</small><b>${value(sensor.battery_pct, "% batteria")} · ${value(sensor.wifi_pct, "% Wi-Fi")}</b></span><p>La proiezione deriva dall'andamento recente della densità e richiede conferma dell'enologo prima di qualsiasi azione.</p></div>${tankSensorHistory(d.wine_history)}`;
};

const toggleTankSensor = () => {
  if (!latestTankData || printMode) return;
  const overlay = ensureTankSensorOverlay();
  if (!overlay.hidden) {
    if (!tankSensorPinned) {
      tankSensorPinned = true;
      clearTimeout(tankSensorTimer);
      overlay.querySelector("#tankSensorMode").textContent = "Fissato · Chiudi per tornare all'etichetta";
      return;
    }
    closeTankSensor();
    return;
  }
  renderTankSensorOverlay(latestTankData);
  overlay.hidden = false;
  document.body.classList.add("tank-sensor-open");
  document.getElementById("liveDot")?.setAttribute("aria-expanded", "true");
  tankSensorPinned = false;
  tankSensorDeadline = Date.now() + 10000;
  clearTimeout(tankSensorTimer);
  tankSensorTimer = setTimeout(closeTankSensor, 10000);
  updateTankSensorCountdown();
};
const wineColor = (row) => {
  const explicit = String(row?.wine_color || "").trim().toLowerCase();
  if (["red", "white", "rose"].includes(explicit)) return explicit;
  const text = `${row?.wine_type || ""} ${row?.content_description || ""} ${row?.wine_lot_name || ""}`.toLowerCase();
  if (/rosato|rosé|rose/.test(text)) return "rose";
  if (/bianco|white|grecanico|carricante/.test(text)) return "white";
  if (/rosso|red|nerello|grenache/.test(text)) return "red";
  return "neutral";
};
const updateConnectionState = (offline) => {
  const subtitle = document.getElementById("tankSubtitle");
  document.body.classList.toggle("offline-cache", offline);
  if (offline) {
    if (!subtitle.textContent.includes("Copia offline")) subtitle.textContent += " · Copia offline";
    document.getElementById("liveDot").style.background = "#d7af36";
  } else {
    document.getElementById("liveDot").style.background = "#55c88b";
  }
};
const printMode = new URLSearchParams(location.search).get("print");
const liveDot = document.getElementById("liveDot");
if (liveDot?.tagName === "BUTTON") {
  liveDot.setAttribute("aria-expanded", "false");
  liveDot.addEventListener("click", toggleTankSensor);
}
document.documentElement.classList.toggle("android-display", /Android/i.test(navigator.userAgent));
try { document.documentElement.classList.toggle("ha-embedded", window.self !== window.top); } catch (_error) { document.documentElement.classList.add("ha-embedded"); }
const syncVisibleHeight = () => {
  if (printMode) return;
  const viewport = window.visualViewport;
  const height = viewport?.height || document.documentElement.clientHeight || window.innerHeight;
  const width = viewport?.width || document.documentElement.clientWidth || window.innerWidth;
  if (Number.isFinite(height) && height > 0) document.documentElement.style.setProperty("--label-visible-height", `${Math.round(height)}px`);
  document.documentElement.classList.toggle("label-compact", width <= 900 || height <= 900);
  document.documentElement.classList.toggle("label-short", height <= 820);
  const phoneLayout = /iPhone|iPod/i.test(navigator.userAgent)
    || (window.matchMedia?.("(pointer:coarse)").matches && Math.min(width, height) <= 520);
  document.documentElement.classList.toggle("label-phone", Boolean(phoneLayout));
  document.documentElement.style.setProperty("--label-visible-width", `${Math.round(width)}px`);
};
syncVisibleHeight();
window.addEventListener("resize", syncVisibleHeight, {passive: true});
window.addEventListener("orientationchange", syncVisibleHeight, {passive: true});
window.visualViewport?.addEventListener("resize", syncVisibleHeight, {passive: true});
if (["a4", "thermal"].includes(printMode)) {
  document.documentElement.classList.add(`print-${printMode}`);
  const pageStyle = document.createElement("style");
  pageStyle.textContent = printMode === "thermal" ? "@page{size:4in 6in;margin:.14in}" : "@page{size:A4 landscape;margin:8mm}";
  document.head.appendChild(pageStyle);
}

if (!printMode && "serviceWorker" in navigator) {
  const gateway = location.pathname.startsWith("/api/baiamonte_labels/") ? "/api/baiamonte_labels" : "";
  let reloadingForWorker = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloadingForWorker) return;
    reloadingForWorker = true;
    location.reload();
  });
  navigator.serviceWorker.register(`${gateway}/service-worker.js?v=${encodeURIComponent(window.BAIAMONTE_DISPLAY_VERSION || "current")}`, {scope: `${gateway}/`})
    .then((registration) => registration.update().then(() => navigator.serviceWorker.ready))
    .then((registration) => registration.active?.postMessage({type: "CACHE_LABEL_PAGE", url: location.href}))
    .catch(() => {});
}

async function refresh() {
  try {
    const kiosk = window.BAIAMONTE_KIOSK_TOKEN;
    const gateway = location.pathname.startsWith("/api/baiamonte_labels/") ? "/api/baiamonte_labels" : "";
    const endpoint = kiosk ? `${gateway}/api/kiosk/${encodeURIComponent(kiosk)}` : `${gateway}/api/tank/${encodeURIComponent(window.BAIAMONTE_TANK_TOKEN)}`;
    const response = await fetch(endpoint, {cache: "no-store"});
    if (!response.ok) throw new Error("Label unavailable");
    const offline = response.headers.get("X-Baiamonte-Offline") === "1";
    if (!offline && "caches" in window) {
      const cacheName = `baiamonte-cellar-label-${window.BAIAMONTE_DISPLAY_VERSION || "current"}`;
      caches.open(cacheName).then((cache) => cache.put(new URL(endpoint, location.href).toString(), response.clone())).catch(() => {});
    }
    const payload = await response.json();
    if (kiosk && !payload.available) {
      document.getElementById("tankTitle").textContent = payload.kiosk?.name || "Cellar tablet";
      document.getElementById("tankSubtitle").textContent = "No tank assigned · configure in Vineyard Operations";
      updateConnectionState(offline);
      return;
    }
    const d = kiosk ? payload.tank : payload;
    latestTankData = d;
    const level = Math.max(0, Math.min(100, Number(d.level_pct) || 0));
    const vessel = vesselType(d.container_type, d.stage);
    const stageClass = cellarStageClass(d.stage || d.processing_phase || d.status);
    const color = wineColor(d);
    const activeFermentation = /ferment|macer|must/.test(String(d.stage || d.processing_phase || "").toLowerCase());
    document.body.classList.toggle("active-fermentation", activeFermentation);
    const transfers = (d.transfers || []).map((row) => new Date(row.transferred_at).toLocaleDateString("it-IT")).join(" · ");
    const parcels = (d.legal_parcels || []).map((parcel) => `<span class="parcel-line"><b>${esc(parcel.legal_reference)}</b><em>${parcel.vineyard_area_ha == null ? "" : `${number(parcel.vineyard_area_ha, 4)} ha vigneto`}${parcel.tenure ? ` · ${esc(parcel.tenure)}` : ""}${parcel.contract_protocol ? ` · Prot. ${esc(parcel.contract_protocol)}` : ""}</em></span>`).join("");
    document.getElementById("tankTitle").textContent = `${d.code} · ${d.name}`;
    const automaticSensor = Boolean(d.plaato) || d.reading_mode === "auto";
    document.getElementById("tankSubtitle").textContent = `${automaticSensor ? "Tank Sensor automatico" : d.reading_mode === "sensor" ? "Sensore Home Assistant" : "Manuale"} · ${d.status || "in uso"}`;
    document.getElementById("labelBody").innerHTML = `
      <article class="vessel vessel-${vessel} wine-${color} stage-${stageClass}">
        <div class="vessel-glow"></div>
        <div class="vessel-top"><small>CONTENITORE · ${esc(vessel)}</small><h2>${esc(d.code)}</h2><span>${esc(d.name)} · ${esc(d.material || "materiale non indicato")}</span></div>
        <div class="vessel-stage">
          <div class="vessel-visual tv-tank-vessel vessel-${vessel} wine-${color}" data-vessel-type="${esc(vessel)}" role="img" aria-label="${esc(vessel)}, ${number(level)}% pieno">
            <i class="wine-fill" style="height:${level}%"><span class="stage-motion" aria-hidden="true"></span></i>${vessel === "fermenter" ? '<span class="vessel-hatch" aria-hidden="true"></span>' : ""}<b class="vessel-level">${number(level)}%</b>
          </div>
          <div class="level-callout"><strong>${number(level)}<small>%</small></strong><span>${activeFermentation ? "Fermentazione attiva" : esc(d.processing_phase || d.stage || "In uso")}</span></div>
        </div>
        <div class="vessel-stats"><span><b>${number(d.capacity_l, 0)} L</b><small>${number(d.capacity_hl, 2)} hL · Capienza</small></span><span><b>${number(d.volume_l)} L</b><small>Contenuto attuale</small></span><span><b>${number(level)}%</b><small>Livello calcolato</small></span></div>
      </article>
      <div class="fields">
        <div class="trend-panel"><div><small>ANDAMENTO RECENTE</small><strong>Ultime letture di cantina</strong></div><div class="micro-chart-grid">${sparkline(d.trends, "temp_c", "Temperatura", "°C")}${sparkline(d.trends, "density_sg", "Densità SG")}${sparkline(d.trends, "brix", "°Brix")}${sparkline(d.trends, "ph", "pH")}</div></div>
        <div class="field wide"><small>Azienda</small><strong>${value(d.legal_company_name)}</strong><span>P.IVA ${value(d.vat_number)} · PEC ${value(d.pec)} · Tel ${value(d.telephone)}</span></div>
        <div class="field wide"><small>Cantiniere</small><strong>${value(d.cantiniere)} <span class="inline-contact">· ${value(d.cantiniere_telephone)}</span></strong></div>
        <div class="field"><small>Vino</small><strong>${value(d.wine_type)}</strong></div><div class="field"><small>Annata</small><strong>${value(d.vintage_year)}</strong></div>
        <div class="field wide"><small>Vitigno / uve</small><strong>${value((d.wine_history?.grape_types || []).join(" / ") || d.variety_summary)}</strong><span>${(d.wine_history?.vintages || []).length} righe storiche collegate</span></div>
        <div class="field"><small>Origine</small><strong>${value(d.origin_country)}</strong></div><div class="field"><small>Denominazione</small><strong>${value(d.denomination_display)}</strong></div>
        <div class="field wide"><small>Contenuto / lotto</small><strong>${value(d.content_description || d.wine_lot_name)}</strong></div>
        <div class="field wide parcel-field"><small>Particelle catastali · ${number((d.legal_parcels || []).length, 0)}</small><strong class="parcel-list">${parcels || "—"}</strong></div>
        <div class="field wide"><small>Fase lavorazione</small><strong>${value(d.processing_phase)}</strong></div>
        <div class="field wide"><small>Prossimo controllo</small><strong>${d.next_check_at ? new Date(d.next_check_at).toLocaleDateString("it-IT") : "—"}</strong></div>
        <div class="field wide"><small>Travasi</small><strong>${value(d.racking_history || transfers)}</strong></div>
        <div class="field wide legal-notes-field"><small>Note legali</small><strong>${value(d.legal_notes)}</strong></div>
        <div class="readings${automaticSensor ? " automatic-sensor-readings" : ""}"><div class="reading"><b>${value(d.temp_c, "°")}</b><small>Temperatura C</small></div><div class="reading"><b>${value(d.density_sg)}</b><small>Densità SG</small></div><div class="reading"><b>${automaticSensor ? value(d.plato, "°P") : value(d.brix)}</b><small>${automaticSensor ? "Tank Sensor Plato" : "°Brix"}</small></div><div class="reading"><b>${automaticSensor ? value(d.fermentation_rate_msg_h, " mSG/h") : value(d.ph)}</b><small>${automaticSensor ? "Attività fermentativa" : "pH"}</small></div>${automaticSensor ? `<div class="reading sensor-health-reading"><b>${value(d.battery_pct, "%")} · ${value(d.wifi_pct, "%")}</b><small>Salute Tank Sensor · batteria / Wi-Fi</small><span>${esc(d.plaato?.batch_name || "Batch non nominato")} · ${esc(d.plaato?.status || "stato non disponibile")}</span></div>` : ""}</div>
      </div>`;
    document.getElementById("updatedAt").textContent = `Aggiornato ${new Date(d.reading_at || d.legal_updated_at || Date.now()).toLocaleString("it-IT")}`;
    updateConnectionState(offline);
    if (!ensureTankSensorOverlay().hidden) renderTankSensorOverlay(d);
    if (printMode && !window.BAIAMONTE_PRINTED) {
      window.BAIAMONTE_PRINTED = true;
      requestAnimationFrame(() => requestAnimationFrame(() => window.print()));
    }
  } catch (error) {
    document.getElementById("liveDot").style.background = "#d76969";
    document.getElementById("tankSubtitle").textContent = "Dati non disponibili · ultimo schermo conservato";
  }
}

refresh();
setInterval(refresh, 30000);
