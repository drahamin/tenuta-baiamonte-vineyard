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
const sparkline = (rows, key, label, suffix = "") => {
  const points = (rows || []).map((row) => row[key]).filter((raw) => raw !== null && raw !== undefined && raw !== "").map(Number).filter(Number.isFinite);
  const latest = points.length ? points.at(-1) : null;
  if (points.length < 2) return `<div class="micro-chart waiting"><small>${label}</small><b>${latest === null ? "—" : `${number(latest, 3)}${suffix}`}</b><span>Storico in attesa</span></div>`;
  const min = Math.min(...points), max = Math.max(...points), spread = max - min || 1;
  const path = points.map((point, index) => `${(index / (points.length - 1) * 100).toFixed(1)},${(31 - ((point - min) / spread * 25)).toFixed(1)}`).join(" ");
  return `<div class="micro-chart"><small>${label}</small><b>${number(latest, 3)}${suffix}</b><svg viewBox="0 0 100 36" preserveAspectRatio="none" role="img" aria-label="Andamento ${label}"><defs><linearGradient id="spark-${key}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e0b92f" stop-opacity=".35"/><stop offset="1" stop-color="#e0b92f" stop-opacity="0"/></linearGradient></defs><polygon points="0,36 ${path} 100,36" fill="url(#spark-${key})"/><polyline points="${path}" fill="none" stroke="#e0b92f" stroke-width="2" vector-effect="non-scaling-stroke"/></svg><span>${points.length} letture</span></div>`;
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
const printMode = new URLSearchParams(location.search).get("print");
const syncVisibleHeight = () => {
  if (printMode) return;
  const height = window.visualViewport?.height || window.innerHeight;
  if (Number.isFinite(height) && height > 0) document.documentElement.style.setProperty("--label-visible-height", `${Math.round(height)}px`);
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

async function refresh() {
  try {
    const kiosk = window.BAIAMONTE_KIOSK_TOKEN;
    const gateway = location.pathname.startsWith("/api/baiamonte_labels/") ? "/api/baiamonte_labels" : "";
    const endpoint = kiosk ? `${gateway}/api/kiosk/${encodeURIComponent(kiosk)}` : `${gateway}/api/tank/${encodeURIComponent(window.BAIAMONTE_TANK_TOKEN)}`;
    const response = await fetch(endpoint, {cache: "no-store"});
    if (!response.ok) throw new Error("Label unavailable");
    const payload = await response.json();
    if (kiosk && !payload.available) {
      document.getElementById("tankTitle").textContent = payload.kiosk?.name || "Cellar tablet";
      document.getElementById("tankSubtitle").textContent = "No tank assigned · configure in Vineyard Operations";
      document.getElementById("liveDot").style.background = "#d7af36";
      return;
    }
    const d = kiosk ? payload.tank : payload;
    const level = Math.max(0, Math.min(100, Number(d.level_pct) || 0));
    const vessel = vesselType(d.container_type, d.stage);
    const activeFermentation = /ferment|macer|must/.test(String(d.stage || d.processing_phase || "").toLowerCase());
    document.body.classList.toggle("active-fermentation", activeFermentation);
    const transfers = (d.transfers || []).map((row) => new Date(row.transferred_at).toLocaleDateString("it-IT")).join(" · ");
    document.getElementById("tankTitle").textContent = `${d.code} · ${d.name}`;
    document.getElementById("tankSubtitle").textContent = `${d.reading_mode === "sensor" ? "Sensore" : "Manuale"} · ${d.status || "in uso"}`;
    document.getElementById("labelBody").innerHTML = `
      <article class="vessel vessel-${vessel} wine-${wineColor(d)}">
        <div class="vessel-glow"></div><div class="vessel-bubbles"></div>
        <div class="vessel-top"><small>CONTENITORE · ${esc(vessel)}</small><h2>${esc(d.code)}</h2><span>${esc(d.name)} · ${esc(d.material || "materiale non indicato")}</span></div>
        <div class="vessel-stage">
          <div class="vessel-visual vessel-${vessel}" role="img" aria-label="${esc(vessel)}, ${number(level)}% pieno">
            <i class="wine-fill" style="height:${level}%"><span></span></i><b class="vessel-hatch"></b><b class="vessel-legs"></b>
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
        <div class="field"><small>Origine</small><strong>${value(d.origin_country)}</strong></div><div class="field"><small>Denominazione</small><strong>${value(d.denomination_display)}</strong></div>
        <div class="field wide"><small>Contenuto / lotto</small><strong>${value(d.content_description || d.wine_lot_name)}</strong></div>
        <div class="field wide"><small>Fase lavorazione</small><strong>${value(d.processing_phase)}</strong></div>
        <div class="field wide"><small>Prossimo controllo</small><strong>${d.next_check_at ? new Date(d.next_check_at).toLocaleDateString("it-IT") : "—"}</strong></div>
        <div class="field wide"><small>Travasi</small><strong>${value(d.racking_history || transfers)}</strong></div>
        <div class="field wide"><small>Note legali</small><strong>${value(d.legal_notes)}</strong></div>
        <div class="readings"><div class="reading"><b>${value(d.temp_c, "°")}</b><small>Temperatura C</small></div><div class="reading"><b>${value(d.density_sg)}</b><small>Densità SG</small></div><div class="reading"><b>${value(d.brix)}</b><small>°Brix</small></div><div class="reading"><b>${value(d.ph)}</b><small>pH</small></div></div>
      </div>`;
    document.getElementById("updatedAt").textContent = `Aggiornato ${new Date(d.reading_at || d.legal_updated_at || Date.now()).toLocaleString("it-IT")}`;
    document.getElementById("liveDot").style.background = "#55c88b";
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
