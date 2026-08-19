/* Cross-dashboard presentation kept separate from the main application bundle. */
(function () {
  const money = value => new Intl.NumberFormat(undefined, {style: 'currency', currency: 'EUR', maximumFractionDigits: 0}).format(Number(value || 0));
  const number = value => new Intl.NumberFormat(undefined, {maximumFractionDigits: 1}).format(Number(value || 0));
  const metrics = payroll => `
    <article class="metric"><span>Approved hours</span><strong>${number(payroll?.approved_hours_ytd)} h</strong><small>${payroll?.year || ''} year to date</small></article>
    <article class="metric"><span>Labor cost</span><strong>${money(payroll?.labor_cost_ytd)}</strong><small>approved this year</small></article>
    <article class="metric"><span>Reimbursements</span><strong>${money(payroll?.reimbursements_ytd)}</strong><small>approved this year</small></article>
    <article class="metric"><span>Ready to pay</span><strong>${money(payroll?.ready_to_pay)}</strong><small>${Number(payroll?.payment_items || 0)} queued records</small></article>
    <article class="metric"><span>Awaiting review</span><strong>${Number(payroll?.awaiting_review || 0)}</strong><small>not yet approved</small></article>
    <article class="metric"><span>Paid</span><strong>${money(payroll?.paid_ytd)}</strong><small>${payroll?.year || ''} year to date</small></article>`;

  const originalFinance = window.renderFinance;
  window.renderFinance = function () {
    originalFinance?.();
    const node = document.getElementById('financePayrollSummary');
    if (node) node.innerHTML = metrics(state?.finance?.payroll || {});
  };

  const originalAdminControl = window.renderAdminControl;
  window.renderAdminControl = function () {
    originalAdminControl?.();
    const node = document.getElementById('adminControlPayroll');
    if (node) node.innerHTML = metrics(state?.adminControl?.payroll || {});
  };

  const originalSocial = window.renderSocial;
  window.renderSocial = function () {
    originalSocial?.();
    const data = state?.social || {};
    [['facebook', data.facebook], ['instagram', data.instagram]].forEach(([name, channel]) => {
      if (!channel?.publishing_ready || channel.connected) return;
      const light = document.querySelector(`#socialLights .system-light:nth-child(${name === 'facebook' ? 1 : 2})`);
      light?.classList.remove('red', 'amber');
      light?.classList.add('green');
      const label = light?.querySelector('small');
      if (label) label.textContent = 'Publishing ready';
      const diagnostic = document.getElementById(`${name}Diagnostic`);
      if (diagnostic) {
        diagnostic.className = 'social-diagnostic good';
        const readbackError = channel.error ? ` ${esc(String(channel.error).slice(0, 180))}` : '';
        diagnostic.innerHTML = `<b>Publishing ready</b><span>Posting works; recent-post readback is currently limited.${readbackError}</span>`;
      }
    });
  };
}());
