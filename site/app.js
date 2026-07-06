// AI×Biology Corpus — vanilla JS filter/search/render
(async function() {
  const PAGE_SIZE = 30;
  let papers = [];
  let stats = null;
  let filteredPapers = [];
  let currentPage = 1;
  const state = {
    q: '',
    venues: new Set(),  // empty = all
    years: new Set(),   // empty = all
    tags: new Set(),    // empty = all
    sort: 'year-desc',
  };

  // ---- Load data ----
  try {
    const [paperResp, statsResp] = await Promise.all([
      fetch('data/papers.json'),
      fetch('data/stats.json'),
    ]);
    papers = await paperResp.json();
    stats = await statsResp.json();
  } catch (e) {
    document.getElementById('results').innerHTML =
      '<div class="empty">Failed to load data. Check that data/papers.json exists.</div>';
    console.error(e);
    return;
  }

  // ---- Hero + Dashboard ----
  document.getElementById('hero-count').textContent = papers.length.toLocaleString();
  const years = [...new Set(papers.map(p => p.y))].sort();
  document.getElementById('hero-years').textContent = `${years[0]}–${years[years.length-1]}`;
  document.getElementById('hero-date').textContent = stats.built_at || '';

  renderDashboard();
  renderVenueChips();
  renderYearChips();
  renderTagChips();
  applyFiltersAndRender();

  // ---- Wire events ----
  document.getElementById('search').addEventListener('input', (e) => {
    state.q = e.target.value.toLowerCase().trim();
    currentPage = 1;
    applyFiltersAndRender();
  });
  document.getElementById('sort').addEventListener('change', (e) => {
    state.sort = e.target.value;
    applyFiltersAndRender();
  });
  document.getElementById('clear-filters').addEventListener('click', clearFilters);

  // ---- Render helpers ----
  function renderDashboard() {
    const dash = document.getElementById('dashboard');
    dash.innerHTML = '';
    const cards = [
      { label: 'Papers total', value: papers.length.toLocaleString() },
      { label: 'Venues', value: '3' },
      { label: 'Years', value: `${years.length}` },
      { label: 'Topic tags', value: (stats.tags || []).length.toString() },
    ];
    if (stats.by_venue) {
      Object.entries(stats.by_venue).forEach(([v, n]) => {
        cards.push({ label: v, value: n.toLocaleString() });
      });
    }
    for (const c of cards) {
      const el = document.createElement('div');
      el.className = 'stat-card';
      el.innerHTML = `<div class="stat-label">${c.label}</div><div class="stat-value">${c.value}</div>`;
      dash.appendChild(el);
    }
  }

  function renderVenueChips() {
    const wrap = document.getElementById('venue-chips');
    wrap.innerHTML = '';
    const venues = ['ICLR', 'ICML', 'NeurIPS'];
    for (const v of venues) {
      const count = papers.filter(p => p.v === v).length;
      if (!count) continue;
      const chip = mkChip(v, count, () => toggleSet(state.venues, v, chip));
      wrap.appendChild(chip);
    }
  }

  function renderYearChips() {
    const wrap = document.getElementById('year-chips');
    wrap.innerHTML = '';
    for (const y of years) {
      const count = papers.filter(p => p.y === y).length;
      if (!count) continue;
      const chip = mkChip(y.toString(), count, () => toggleSet(state.years, y, chip));
      wrap.appendChild(chip);
    }
  }

  function renderTagChips() {
    const wrap = document.getElementById('tag-chips');
    wrap.innerHTML = '';
    // Show top ~20 tags
    const tagList = (stats.tags || []).slice(0, 25);
    for (const [tag, count] of tagList) {
      const chip = mkChip(tag, count, () => toggleSet(state.tags, tag, chip));
      wrap.appendChild(chip);
    }
  }

  function mkChip(label, count, onClick) {
    const el = document.createElement('button');
    el.className = 'chip';
    el.type = 'button';
    el.innerHTML = `${label}<span class="chip-count">${count}</span>`;
    el.addEventListener('click', () => {
      el.classList.toggle('active');
      onClick();
    });
    return el;
  }

  function toggleSet(set, item, chipEl) {
    if (set.has(item)) set.delete(item);
    else set.add(item);
    currentPage = 1;
    applyFiltersAndRender();
  }

  function clearFilters() {
    state.q = '';
    state.venues.clear();
    state.years.clear();
    state.tags.clear();
    state.sort = 'year-desc';
    document.getElementById('search').value = '';
    document.getElementById('sort').value = 'year-desc';
    document.querySelectorAll('.chip.active').forEach(c => c.classList.remove('active'));
    currentPage = 1;
    applyFiltersAndRender();
  }

  // ---- Filter & render ----
  function applyFiltersAndRender() {
    const q = state.q;
    let out = papers;
    if (q) {
      out = out.filter(p =>
        (p.t || '').toLowerCase().includes(q) ||
        (p.a || '').toLowerCase().includes(q)
      );
    }
    if (state.venues.size) out = out.filter(p => state.venues.has(p.v));
    if (state.years.size) out = out.filter(p => state.years.has(p.y));
    if (state.tags.size) out = out.filter(p => (p.g || []).some(tag => state.tags.has(tag)));

    // Sort
    out = [...out];
    if (state.sort === 'year-desc') out.sort((a, b) => b.y - a.y || (a.t || '').localeCompare(b.t || ''));
    else if (state.sort === 'year-asc') out.sort((a, b) => a.y - b.y || (a.t || '').localeCompare(b.t || ''));
    else if (state.sort === 'title') out.sort((a, b) => (a.t || '').localeCompare(b.t || ''));

    filteredPapers = out;

    document.getElementById('result-count').textContent = out.length.toLocaleString();
    document.getElementById('active-filters').textContent = activeFilterSummary();
    renderPage();
    renderPagination();
  }

  function activeFilterSummary() {
    const parts = [];
    if (state.q) parts.push(`search: "${state.q}"`);
    if (state.venues.size) parts.push(`venue: ${[...state.venues].join(', ')}`);
    if (state.years.size) parts.push(`year: ${[...state.years].sort().join(', ')}`);
    if (state.tags.size) parts.push(`tag: ${[...state.tags].join(', ')}`);
    return parts.length ? ' · ' + parts.join(' · ') : '';
  }

  function renderPage() {
    const wrap = document.getElementById('results');
    if (filteredPapers.length === 0) {
      wrap.innerHTML = '<div class="empty">No papers match these filters.</div>';
      return;
    }
    const start = (currentPage - 1) * PAGE_SIZE;
    const slice = filteredPapers.slice(start, start + PAGE_SIZE);
    wrap.innerHTML = slice.map(paperCard).join('');
    // Bind expand
    wrap.querySelectorAll('.card-abstract').forEach(el =>
      el.addEventListener('click', () => el.classList.toggle('expanded'))
    );
  }

  function paperCard(p) {
    const authors = (p.au || []).slice(0, 6).join(', ') + ((p.au || []).length > 6 ? ', et al.' : '');
    const tags = (p.g || []).map(t => `<span class="tag">${t}</span>`).join('');
    const abstract = p.a ? `<p class="card-abstract">${escapeHtml(p.a)}</p>` : '';
    const links = [];
    if (p.u) links.push(`<a href="${p.u}" target="_blank" rel="noopener">Page ↗</a>`);
    if (p.d) links.push(`<a href="${p.d}" target="_blank" rel="noopener">PDF ↗</a>`);
    return `<article class="card">
      <div class="card-header">
        <span class="venue-badge venue-${p.v}">${p.v} ${p.y}</span>
      </div>
      <h3 class="card-title">${escapeHtml(p.t)}</h3>
      <div class="card-authors">${escapeHtml(authors)}</div>
      <div class="card-tags">${tags}</div>
      ${abstract}
      <div class="card-links">${links.join(' · ')}</div>
    </article>`;
  }

  function renderPagination() {
    const wrap = document.getElementById('pagination');
    wrap.innerHTML = '';
    const totalPages = Math.ceil(filteredPapers.length / PAGE_SIZE);
    if (totalPages <= 1) return;
    // Prev
    const prev = mkPagBtn('«', currentPage > 1, () => { currentPage--; renderPage(); renderPagination(); window.scrollTo({top: 0, behavior: 'smooth'}); });
    wrap.appendChild(prev);
    // Page numbers (compact)
    const pages = new Set([1, totalPages, currentPage, currentPage-1, currentPage+1, currentPage-2, currentPage+2]);
    const sorted = [...pages].filter(p => p >= 1 && p <= totalPages).sort((a,b) => a-b);
    let prevP = 0;
    for (const p of sorted) {
      if (p - prevP > 1) {
        const dots = document.createElement('span');
        dots.textContent = '…';
        dots.style.padding = '0 0.35rem';
        wrap.appendChild(dots);
      }
      const btn = mkPagBtn(p.toString(), true, () => { currentPage = p; renderPage(); renderPagination(); window.scrollTo({top: 0, behavior: 'smooth'}); });
      if (p === currentPage) btn.classList.add('active');
      wrap.appendChild(btn);
      prevP = p;
    }
    const next = mkPagBtn('»', currentPage < totalPages, () => { currentPage++; renderPage(); renderPagination(); window.scrollTo({top: 0, behavior: 'smooth'}); });
    wrap.appendChild(next);
  }

  function mkPagBtn(label, enabled, onClick) {
    const b = document.createElement('button');
    b.textContent = label;
    b.disabled = !enabled;
    b.addEventListener('click', onClick);
    return b;
  }

  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
  }
})();
