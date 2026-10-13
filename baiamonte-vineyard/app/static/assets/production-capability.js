(function () {
  const number = value => Number(value || 0).toLocaleString(undefined, {maximumFractionDigits: 2});
  const escape = value => String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[character]));

  window.renderProductionCapability = function renderProductionCapability(nodeId, capability) {
    const node = document.getElementById(nodeId);
    if (!node) return;
    if (!capability) {
      node.innerHTML = "<h3>Production capability</h3><p>Capability records are not available for this vintage.</p>";
      return;
    }
    const vessels = capability.vessels || {};
    const streams = capability.streams || [];
    const legal = capability.legal_scenarios || [];
    const warnings = capability.warnings || [];
    node.innerHTML = `
      <div class="chart-heading"><div>
        <p class="eyebrow dark">ACTUALS · VESSELS · CONDITIONAL LEGAL CEILINGS</p>
        <h3>Production capability</h3>
        <span>Measured production stays separate from planning and documentary maximums</span>
      </div></div>
      <div class="metric-grid compact-metrics">
        <article class="metric"><span>Fruit received</span><strong>${number(capability.fruit_received_kg)} kg</strong><small>estate + purchased</small></article>
        <article class="metric"><span>Measured wine / must</span><strong>${number(capability.measured_wine_l)} L</strong><small>recorded liquid only</small></article>
        <article class="metric"><span>Full ${number(capability.bottle_size_ml)} ml bottles</span><strong>${number(capability.full_bottle_equivalents)}</strong><small>from measured volume only</small></article>
        <article class="metric"><span>Working vessel space</span><strong>${number(vessels.available_working_capacity_l)} L</strong><small>${number(vessels.recorded_occupancy_l)} / ${number(vessels.working_capacity_l)} L at ${number(vessels.working_fill_pct)}%</small></article>
      </div>
      <div class="list">${streams.map(row => `<div class="vintage-row">
        <div><b>${escape(row.variety_name)}</b><small>${number(row.estate_fruit_kg)} kg estate · ${number(row.purchased_fruit_kg)} kg purchased${row.unmeasured_lot_count ? ` · ${row.unmeasured_lot_count} volume pending` : ""}</small></div>
        <div><span>Fruit</span><b>${number(row.fruit_received_kg)} kg</b></div>
        <div><span>Measured</span><b>${number(row.measured_wine_l)} L</b></div>
        <div><span>750 ml</span><b>${number(row.full_bottle_equivalents)}</b></div>
        <strong>${row.observed_l_per_kg == null ? "—" : `${number(row.observed_l_per_kg)} L/kg`}</strong>
      </div>`).join("")}</div>
      ${warnings.map(message => `<p class="safety-note">${escape(message)}</p>`).join("")}
      <details><summary>Documentary legal scenarios (${legal.length})</summary>
        <p class="safety-note">Alternatives are not additive and do not establish current entitlement.</p>
        <div class="list">${legal.map(row => `<div class="list-row"><span class="list-icon">§</span><div>
          <b>${escape(row.scenario_label)}</b>
          <small>${escape(row.denomination)} · ${escape(String(row.eligibility_status || "").replaceAll("_", " "))} · ${number(row.grapes_kg)} kg → ${number(row.wine_l)} L · ${number(row.full_bottles_750ml)} full bottles</small>
          <small>${escape(row.caveat || "")}</small>
        </div></div>`).join("")}</div>
      </details>
      <small>${escape(capability.basis || "")}</small>`;
  };
}());
