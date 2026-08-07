/* Keep essential controls usable even if a later feature initializer fails. */
(() => {
  const byId = id => document.getElementById(id);

  function activateView(button) {
    const view = button?.dataset?.view;
    if (!view) return;
    document.querySelectorAll('.tabs button').forEach(item => item.classList.toggle('active', item === button));
    document.querySelectorAll('.view').forEach(item => item.classList.toggle('active', item.id === `view-${view}`));
    const renderers = {
      weather: 'renderWeather',
      lab: 'renderLabTrends',
      harvest: 'renderGrapes',
      projections: 'renderProjections',
      olives: 'renderOlives',
      history: 'renderHistory',
    };
    const renderer = window[renderers[view]];
    if (typeof renderer === 'function') setTimeout(renderer, 0);
  }

  document.querySelectorAll('.tabs button').forEach(button => {
    button.addEventListener('click', () => activateView(button));
  });

  const refresh = byId('refresh');
  if (refresh && typeof refresh.onclick !== 'function' && typeof window.loadAll === 'function') {
    refresh.addEventListener('click', window.loadAll);
  }

  const year = byId('year');
  if (year && typeof year.onchange !== 'function' && typeof window.loadAll === 'function' && typeof state !== 'undefined') {
    year.addEventListener('change', async () => {
      state.year = Number(year.value);
      await window.loadAll();
    });
  }

  document.querySelectorAll('[data-open]').forEach(button => {
    if (typeof button.onclick !== 'function' && typeof window.openEntry === 'function') {
      button.addEventListener('click', () => window.openEntry(button.dataset.open));
    }
  });
  document.querySelectorAll('[data-record]').forEach(button => {
    if (typeof button.onclick !== 'function' && typeof window.openRecords === 'function') {
      button.addEventListener('click', () => window.openRecords(button.dataset.record));
    }
  });
})();
