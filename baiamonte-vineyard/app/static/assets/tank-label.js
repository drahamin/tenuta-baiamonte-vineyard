const esc = (value) => String(value ?? "—").replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const value = (raw, suffix = "") => raw === null || raw === undefined || raw === "" ? "—" : `${esc(raw)}${suffix}`;

async function refresh() {
  try {
    const kiosk = window.BAIAMONTE_KIOSK_TOKEN;
    const endpoint = kiosk ? `/api/kiosk/${encodeURIComponent(kiosk)}` : `/api/tank/${encodeURIComponent(window.BAIAMONTE_TANK_TOKEN)}`;
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
    const transfers = (d.transfers || []).map((row) => new Date(row.transferred_at).toLocaleDateString("it-IT")).join(" · ");
    document.getElementById("tankTitle").textContent = `${d.code} · ${d.name}`;
    document.getElementById("tankSubtitle").textContent = `${d.reading_mode === "sensor" ? "Sensore" : "Manuale"} · ${d.status || "in uso"}`;
    document.getElementById("labelBody").innerHTML = `
      <article class="vessel ${esc(d.container_type || "tank")}">
        <div class="vessel-glow"></div><div class="vessel-bubbles"></div>
        <div class="vessel-top"><small>CONTENITORE · ${esc(d.container_type)}</small><h2>${esc(d.code)}</h2><span>${esc(d.material || d.name)}</span></div>
        <div class="fill-shell"><i class="wine-fill" style="height:${Math.max(0, Math.min(100, Number(d.level_pct) || 0))}%"></i><em></em></div>
        <div class="vessel-stats"><span><b>${value(d.capacity_hl)}</b><small>Capienza hL</small></span><span><b>${value(d.volume_l, " L")}</b><small>Contenuto</small></span><span><b>${value(d.level_pct, "%")}</b><small>Livello</small></span></div>
      </article>
      <div class="fields">
        <div class="field"><small>Vino</small><strong>${value(d.wine_type)}</strong></div><div class="field"><small>Annata</small><strong>${value(d.vintage_year)}</strong></div>
        <div class="field"><small>Origine</small><strong>${value(d.origin_country)}</strong></div><div class="field"><small>Denominazione</small><strong>${value(d.denomination_display)}</strong></div>
        <div class="field wide"><small>Contenuto / lotto</small><strong>${value(d.content_description || d.wine_lot_name)}</strong></div>
        <div class="field wide"><small>Fase lavorazione</small><strong>${value(d.processing_phase)}</strong></div>
        <div class="field wide"><small>Travasi</small><strong>${value(d.racking_history || transfers)}</strong></div>
        <div class="readings"><div class="reading"><b>${value(d.temp_c, "°")}</b><small>Temperatura C</small></div><div class="reading"><b>${value(d.density_sg)}</b><small>Densità SG</small></div><div class="reading"><b>${value(d.brix)}</b><small>°Brix</small></div><div class="reading"><b>${value(d.ph)}</b><small>pH</small></div></div>
      </div>`;
    document.getElementById("updatedAt").textContent = `Aggiornato ${new Date(d.reading_at || d.legal_updated_at || Date.now()).toLocaleString("it-IT")}`;
    document.getElementById("liveDot").style.background = "#55c88b";
  } catch (error) {
    document.getElementById("liveDot").style.background = "#d76969";
    document.getElementById("tankSubtitle").textContent = "Dati non disponibili · ultimo schermo conservato";
  }
}

refresh();
setInterval(refresh, 30000);
