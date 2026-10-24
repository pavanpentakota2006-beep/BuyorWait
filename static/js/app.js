/**
 * Buy or Wait? — Decision Intelligence Client Application
 * Dynamic Single Page Application on port 5176
 */

let allRequests = [];
let allSamples = [];
let sampleBenchmarkFilter = 'all';
let benchmarkCurrencyFilter = 'all';
let userProfilesMap = {};
let ratesMap = {};

// --------------------------------------------------------------------------
// Toast Notification System
// --------------------------------------------------------------------------
function showToast(msg, type = 'cyan', icon = '✦') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span style="font-size:16px;">${icon}</span><span>${msg}</span>`;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3100);
}

// --------------------------------------------------------------------------
// Animated Counter for KPI values
// --------------------------------------------------------------------------
function animateCount(el, targetVal, prefix = '', suffix = '', decimals = 0) {
  if (!el) return;
  const start = 0;
  const duration = 800;
  const startTime = performance.now();
  const format = (v) => {
    const n = decimals > 0 ? v.toFixed(decimals) : Math.round(v);
    return `${prefix}${Number(n).toLocaleString()}${suffix}`;
  };
  const step = (now) => {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    el.textContent = format(eased * targetVal);
    if (progress < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// --------------------------------------------------------------------------
// Live Engine Clock
// --------------------------------------------------------------------------
function startEngineClock() {
  const clockEl = document.getElementById('sidebar-clock');
  if (!clockEl) return;
  const update = () => {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString('en-US', { hour12: false });
  };
  update();
  setInterval(update, 1000);
}

document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initTheme();
  initShortcuts();
  startEngineClock();
  loadProfiles();
  loadOverview();
  loadRequests();
  loadSamples();
  loadRates();
});

// --------------------------------------------------------------------------
// Navigation & Tab Switching
// --------------------------------------------------------------------------
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const targetTab = item.getAttribute('data-tab');
      switchTab(targetTab);
    });
  });
}

function switchTab(tabId) {
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
  });
  document.querySelectorAll('.tab-view').forEach(view => {
    view.classList.toggle('active', view.id === `view-${tabId}`);
  });
}

// --------------------------------------------------------------------------
// Theme Toggle
// --------------------------------------------------------------------------
function initTheme() {
  const toggleBtn = document.getElementById('theme-toggle');
  if (!toggleBtn) return;
  toggleBtn.addEventListener('click', () => {
    document.body.classList.toggle('light-theme');
    document.body.classList.toggle('dark-theme');
  });
}

// --------------------------------------------------------------------------
// Keyboard Shortcuts (Ctrl+K)
// --------------------------------------------------------------------------
function initShortcuts() {
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      openSearch();
    }
    if (e.key === 'Escape') {
      closeModal();
      closeSearchPalette();
    }
  });
}

// --------------------------------------------------------------------------
// Overview Telemetry
// --------------------------------------------------------------------------
async function loadOverview() {
  try {
    const res = await fetch('/api/overview');
    const data = await res.parse ? await res.json() : await res.json();

    document.getElementById('kpi-total-requests').textContent = data.total_requests;
    
    const nowCount = data.status_breakdown['affordable_now'] || 0;
    const planCount = data.status_breakdown['affordable_with_plan'] || 0;
    
    // Animate KPI counters
    animateCount(document.getElementById('kpi-total-requests'), data.total_requests);
    animateCount(document.getElementById('kpi-affordable-now'), nowCount);
    animateCount(document.getElementById('kpi-affordable-plan'), planCount);
    
    document.getElementById('kpi-safe-capital').textContent = `$${(data.total_safe_usd).toLocaleString()}`;
    document.getElementById('kpi-capital-ratio').textContent = `${data.safe_ratio_pct}% Capital Safety Ratio`;

    // Status distribution
    const statusContainer = document.getElementById('status-distribution-container');
    statusContainer.innerHTML = '';
    const statusColors = {
      'affordable_now': { fill: 'var(--emerald)', label: 'Affordable Now' },
      'affordable_with_plan': { fill: 'var(--cyan)', label: 'Affordable with Plan' },
      'affordable_later': { fill: 'var(--amber)', label: 'Affordable Later' },
      'not_affordable': { fill: 'var(--rose)', label: 'Not Affordable' }
    };

    for (const [key, conf] of Object.entries(statusColors)) {
      const count = data.status_breakdown[key] || 0;
      const pct = ((count / data.total_requests) * 100).toFixed(1);
      statusContainer.innerHTML += `
        <div class="dist-item">
          <div class="dist-labels">
            <span>${conf.label}</span>
            <span style="color: ${conf.fill};">${count} (${pct}%)</span>
          </div>
          <div class="dist-bar-track">
            <div class="dist-bar-fill" style="width: ${pct}%; background-color: ${conf.fill};"></div>
          </div>
        </div>
      `;
    }

    // Method distribution
    const methodContainer = document.getElementById('method-distribution-container');
    methodContainer.innerHTML = '';
    const methodColors = {
      'full_payment': { fill: 'var(--emerald)', label: 'Full Payment' },
      'installments': { fill: 'var(--cyan)', label: 'Installments' },
      'partial_payment': { fill: 'var(--blue)', label: 'Partial Payment' },
      'wait': { fill: 'var(--amber)', label: 'Wait' },
      'not_recommended': { fill: 'var(--rose)', label: 'Not Recommended' }
    };

    for (const [key, conf] of Object.entries(methodColors)) {
      const count = data.method_breakdown[key] || 0;
      const pct = ((count / data.total_requests) * 100).toFixed(1);
      methodContainer.innerHTML += `
        <div class="dist-item">
          <div class="dist-labels">
            <span>${conf.label}</span>
            <span style="color: ${conf.fill};">${count} (${pct}%)</span>
          </div>
          <div class="dist-bar-track">
            <div class="dist-bar-fill" style="width: ${pct}%; background-color: ${conf.fill};"></div>
          </div>
        </div>
      `;
    }

    // Currency distribution
    const curContainer = document.getElementById('currency-distribution-container');
    curContainer.innerHTML = '';
    for (const [cur, count] of Object.entries(data.currency_breakdown)) {
      const pct = ((count / data.total_requests) * 100).toFixed(1);
      curContainer.innerHTML += `
        <div class="dist-item">
          <div class="dist-labels">
            <span>${cur} Requests</span>
            <span class="text-cyan">${count} (${pct}%)</span>
          </div>
          <div class="dist-bar-track">
            <div class="dist-bar-fill" style="width: ${pct}%; background-color: var(--cyan);"></div>
          </div>
        </div>
      `;
    }

  } catch (err) {
    console.error('Error loading overview:', err);
  }
}

// --------------------------------------------------------------------------
// Decision Explorer
// --------------------------------------------------------------------------
async function loadRequests() {
  try {
    const res = await fetch('/api/requests?limit=250');
    const data = await res.json();
    allRequests = data.requests || [];

    renderRequestsTable(allRequests);
    populateUserPickers(allRequests);

    // Setup filter listeners with smart coordination
    const searchInput = document.getElementById('explorer-search');
    const statusSelect = document.getElementById('filter-status');
    const methodSelect = document.getElementById('filter-method');
    const curSelect = document.getElementById('filter-currency');

    if (searchInput) searchInput.addEventListener('input', applyFilters);
    if (statusSelect) statusSelect.addEventListener('change', onStatusFilterChange);
    if (methodSelect) methodSelect.addEventListener('change', onMethodFilterChange);
    if (curSelect) curSelect.addEventListener('change', applyFilters);

  } catch (err) {
    console.error('Error loading requests:', err);
  }
}

function setExplorerFilters(status = 'all', method = 'all', cur = 'all') {
  const statusEl = document.getElementById('filter-status');
  const methodEl = document.getElementById('filter-method');
  const curEl = document.getElementById('filter-currency');
  const searchEl = document.getElementById('explorer-search');

  if (statusEl) statusEl.value = status;
  if (methodEl) methodEl.value = method;
  if (curEl) curEl.value = cur;
  if (searchEl && status === 'all' && method === 'all' && cur === 'all') {
    searchEl.value = '';
  }

  updateExplorerChipStates(status, method);
  applyFilters();
}

function resetExplorerFilters() {
  setExplorerFilters('all', 'all', 'all');
  showToast('Showing all 250 requests', 'cyan', '↺');
}

function updateExplorerChipStates(status, method) {
  document.querySelectorAll('#view-explorer .filter-chips .chip').forEach(c => c.classList.remove('active'));

  if (status === 'all' && method === 'all') {
    const allChip = document.getElementById('chip-exp-all');
    if (allChip) allChip.classList.add('active');
  } else if (status === 'affordable_now') {
    const chip = document.getElementById('chip-exp-affordable_now');
    if (chip) chip.classList.add('active');
  } else if (status === 'affordable_with_plan') {
    const chip = document.getElementById('chip-exp-affordable_with_plan');
    if (chip) chip.classList.add('active');
  } else if (method === 'installments') {
    const chip = document.getElementById('chip-exp-installments');
    if (chip) chip.classList.add('active');
  } else if (status === 'not_affordable') {
    const chip = document.getElementById('chip-exp-not_affordable');
    if (chip) chip.classList.add('active');
  } else if (status === 'affordable_later') {
    const chip = document.getElementById('chip-exp-affordable_later');
    if (chip) chip.classList.add('active');
  }
}

function onStatusFilterChange() {
  const statusEl = document.getElementById('filter-status');
  const methodEl = document.getElementById('filter-method');
  if (!statusEl || !methodEl) return;

  const st = statusEl.value;
  const mt = methodEl.value;

  // Incompatible combinations auto-resolve so users never get an accidental 0-result lock:
  if (st === 'affordable_now' && mt !== 'all' && mt !== 'full_payment') {
    methodEl.value = 'all';
    showToast('Payment method set to All (Affordable Now uses Full Payment)', 'cyan', 'ℹ');
  } else if (st === 'affordable_with_plan' && mt !== 'all' && mt !== 'installments' && mt !== 'partial_payment') {
    methodEl.value = 'all';
  } else if (st === 'not_affordable' && mt !== 'all' && mt !== 'not_recommended') {
    methodEl.value = 'all';
  } else if (st === 'affordable_later' && mt !== 'all' && mt !== 'wait') {
    methodEl.value = 'all';
  }

  updateExplorerChipStates(st, methodEl.value);
  applyFilters();
}

function onMethodFilterChange() {
  const statusEl = document.getElementById('filter-status');
  const methodEl = document.getElementById('filter-method');
  if (!statusEl || !methodEl) return;

  const st = statusEl.value;
  const mt = methodEl.value;

  if (mt === 'installments' && st !== 'affordable_with_plan') {
    statusEl.value = 'affordable_with_plan';
    showToast('Status adjusted to Affordable with Plan (matches Installments)', 'cyan', 'ℹ');
  } else if (mt === 'full_payment' && st !== 'affordable_now') {
    statusEl.value = 'affordable_now';
    showToast('Status adjusted to Affordable Now (matches Full Payment)', 'cyan', 'ℹ');
  } else if (mt === 'not_recommended' && st !== 'not_affordable') {
    statusEl.value = 'not_affordable';
  } else if (mt === 'wait' && st !== 'affordable_later') {
    statusEl.value = 'affordable_later';
  } else if (mt === 'partial_payment' && st !== 'affordable_with_plan') {
    statusEl.value = 'affordable_with_plan';
  }

  updateExplorerChipStates(statusEl.value, mt);
  applyFilters();
}

function renderRequestsTable(reqs) {
  const tbody = document.getElementById('requests-table-body');
  tbody.innerHTML = '';

  const countEl = document.getElementById('showing-count-text');
  if (countEl) {
    if (reqs.length === allRequests.length) {
      countEl.innerHTML = `Showing all <strong>${allRequests.length}</strong> of ${allRequests.length} requests`;
    } else {
      countEl.innerHTML = `Showing <strong>${reqs.length}</strong> of ${allRequests.length} requests · <a href="javascript:void(0)" onclick="resetExplorerFilters()" style="color:var(--cyan); text-decoration:underline; cursor:pointer;">Reset to show all 250</a>`;
    }
  }

  if (!reqs || reqs.length === 0) {
    const q = document.getElementById('explorer-search')?.value.trim() || '';
    const status = document.getElementById('filter-status')?.value || 'all';
    const method = document.getElementById('filter-method')?.value || 'all';
    const cur = document.getElementById('filter-currency')?.value || 'all';

    tbody.innerHTML = `
      <tr>
        <td colspan="9" style="text-align: center; padding: 48px 20px;">
          <div style="max-width: 520px; margin: 0 auto; background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); padding: 32px 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);">
            <div style="font-size: 38px; margin-bottom: 12px;">🔍</div>
            <h3 style="font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px;">No matching requests found</h3>
            <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 20px;">
              No requests match the current criteria:
              <span style="color: var(--cyan); font-family: var(--font-mono);">${q ? `search "${q}", ` : ''}status: ${status}, method: ${method}, currency: ${cur}</span>.
            </p>
            <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
              <button class="btn btn-primary btn-sm" onclick="resetExplorerFilters()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
                <span>Show All 250 Requests</span>
              </button>
              <button class="btn btn-secondary btn-sm" onclick="setExplorerFilters('affordable_now', 'all', 'all')">
                <span>View 73 Affordable Now</span>
              </button>
              <button class="btn btn-secondary btn-sm" onclick="setExplorerFilters('affordable_with_plan', 'installments', 'all')">
                <span>View 44 Installments</span>
              </button>
            </div>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  reqs.forEach(r => {
    const tr = document.createElement('tr');
    tr.style.cursor = 'pointer';

    const statusBadge = getStatusBadge(r.affordability_status);
    const methodBadge = getMethodBadge(r.recommended_payment_method);
    const amountFmt = `${r.requested_currency} ${r.requested_amount.toLocaleString()}`;
    const safeFmt = `${r.home_currency} ${r.amount_safe_to_pay.toLocaleString()}`;

    tr.innerHTML = `
      <td><strong class="font-mono text-cyan">${r.request_id}</strong></td>
      <td><span class="font-mono">${r.user_id}</span></td>
      <td><strong>${amountFmt}</strong></td>
      <td><span class="text-emerald">${safeFmt}</span></td>
      <td>${statusBadge}</td>
      <td>${methodBadge}</td>
      <td>${r.earliest_date_for_full_payment || '<span style="color: var(--text-muted);">None</span>'}</td>
      <td style="max-width: 280px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${r.decision_explanation}">${r.decision_explanation}</td>
      <td>
        <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); inspectRequest('${r.request_id}')">
          Deep Dive
        </button>
      </td>
    `;

    tr.addEventListener('click', () => inspectRequest(r.request_id));
    tbody.appendChild(tr);
  });
}

function applyFilters() {
  const q = document.getElementById('explorer-search')?.value.toLowerCase().trim() || '';
  const status = document.getElementById('filter-status')?.value || 'all';
  const method = document.getElementById('filter-method')?.value || 'all';
  const cur = document.getElementById('filter-currency')?.value || 'all';

  const filtered = allRequests.filter(r => {
    const matchesSearch = !q || (
      r.request_id.toLowerCase().includes(q) ||
      r.user_id.toLowerCase().includes(q) ||
      (r.item_description && r.item_description.toLowerCase().includes(q)) ||
      (r.category && r.category.toLowerCase().includes(q))
    );
    const matchesStatus = (status === 'all' || r.affordability_status === status);
    const matchesMethod = (method === 'all' || r.recommended_payment_method === method);
    const matchesCur = (cur === 'all' || r.requested_currency === cur);

    return matchesSearch && matchesStatus && matchesMethod && matchesCur;
  });

  renderRequestsTable(filtered);
}

function getStatusBadge(st) {
  switch(st) {
    case 'affordable_now': return '<span class="badge badge-emerald">Affordable Now</span>';
    case 'affordable_with_plan': return '<span class="badge badge-cyan">Affordable with Plan</span>';
    case 'affordable_later': return '<span class="badge badge-amber">Affordable Later</span>';
    default: return '<span class="badge badge-rose">Not Affordable</span>';
  }
}

function getMethodBadge(m) {
  switch(m) {
    case 'full_payment': return '<span class="badge badge-emerald">Full Payment</span>';
    case 'installments': return '<span class="badge badge-cyan">Installments</span>';
    case 'partial_payment': return '<span class="badge badge-blue">Partial Payment</span>';
    case 'wait': return '<span class="badge badge-amber">Wait</span>';
    default: return '<span class="badge badge-rose">Not Recommended</span>';
  }
}

// --------------------------------------------------------------------------
// Deep Dive Modal
// --------------------------------------------------------------------------
async function inspectRequest(reqId) {
  try {
    const modal = document.getElementById('deepdive-modal');
    const res = await fetch(`/api/requests/${reqId}`);
    const data = await res.json();
    const req = data.request;
    const fc = data.forecast;

    document.getElementById('modal-req-id').textContent = `${req.request_id} — ${req.item_description || req.category}`;
    document.getElementById('modal-req-user').textContent = `User: ${req.user_id} · Request Date: ${req.request_date} · Target Completion: ${req.desired_completion_date}`;

    const body = document.getElementById('modal-body-content');
    body.innerHTML = `
      <div class="telemetry-strip" style="margin-bottom: 0;">
        <div class="strip-card">
          <span class="strip-label">Requested</span>
          <span class="strip-value text-cyan">${req.requested_currency} ${req.requested_amount.toLocaleString()}</span>
        </div>
        <div class="strip-card">
          <span class="strip-label">Safe-to-Pay Limit Today</span>
          <span class="strip-value text-emerald">${req.home_currency} ${req.amount_safe_to_pay.toLocaleString()}</span>
        </div>
        <div class="strip-card">
          <span class="strip-label">Affordability Status</span>
          <div style="margin-top: 6px;">${getStatusBadge(req.affordability_status)}</div>
        </div>
        <div class="strip-card">
          <span class="strip-label">Recommended Method</span>
          <div style="margin-top: 6px;">${getMethodBadge(req.recommended_payment_method)}</div>
        </div>
      </div>

      <div class="sim-decision-box">
        <span class="box-title">Deterministic Decision Reason</span>
        <p>${req.decision_explanation}</p>
      </div>

      <div class="sim-details-grid">
        <div class="detail-box">
          <span class="lbl">Payment Plan</span>
          <span class="val font-mono">${req.payment_plan}</span>
        </div>
        <div class="detail-box">
          <span class="lbl">Earliest Full Payment Date</span>
          <span class="val">${req.earliest_date_for_full_payment || 'N/A'}</span>
        </div>
        <div class="detail-box">
          <span class="lbl">Spending Changes Needed</span>
          <span class="val">${req.spending_changes_needed}</span>
        </div>
        <div class="detail-box">
          <span class="lbl">Current Available Balance</span>
          <span class="val">${req.home_currency} ${req.current_available_balance.toLocaleString()} (Min Reserve: ${req.minimum_balance_to_keep.toLocaleString()})</span>
        </div>
      </div>

      ${data.payment_options.length > 0 ? `
        <div>
          <h4 style="font-size: 14px; margin-bottom: 10px; color: var(--text-secondary);">Supplied Payment Options (${data.payment_options.length})</h4>
          <table class="data-table" style="font-size: 12px;">
            <thead>
              <tr>
                <th>Option ID</th>
                <th>Method</th>
                <th>Payments</th>
                <th>Each Amount</th>
                <th>First Date</th>
                <th>Freq</th>
              </tr>
            </thead>
            <tbody>
              ${data.payment_options.map(o => `
                <tr>
                  <td class="font-mono text-cyan">${o.payment_option_id}</td>
                  <td>${o.payment_method}</td>
                  <td>${o.number_of_payments}</td>
                  <td>${o.payment_amount.toLocaleString()}</td>
                  <td>${o.first_payment_date}</td>
                  <td>${o.payment_frequency_days}d</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      ` : ''}

      ${fc ? `
        <div>
          <h4 style="font-size: 14px; margin-bottom: 10px; color: var(--text-secondary);">90-Day Cash Runway Preview</h4>
          <div class="svg-chart-container" style="height: 180px;">
            <svg id="modal-runway-svg" viewBox="0 0 800 200" preserveAspectRatio="none"></svg>
          </div>
        </div>
      ` : ''}
    `;

    modal.classList.add('active');

    if (fc && fc.timeline) {
      renderSvgChart('modal-runway-svg', fc.timeline, fc.min_balance);
    }

  } catch (err) {
    console.error('Error inspecting request:', err);
  }
}

function closeModal(e) {
  const modal = document.getElementById('deepdive-modal');
  if (modal) modal.classList.remove('active');
}

// --------------------------------------------------------------------------
// 90-Day Cash Runway & User Profile Loading
// --------------------------------------------------------------------------
async function loadProfiles() {
  try {
    const res = await fetch('/api/profiles');
    const data = await res.json();
    const profiles = data.profiles || [];
    const simUserSelect = document.getElementById('sim-user-id');

    if (profiles.length > 0) {
      profiles.forEach(p => {
        userProfilesMap[p.user_id] = p.home_currency;
      });

      if (simUserSelect) {
        const prevVal = simUserSelect.value || 'user_49';
        simUserSelect.innerHTML = '';
        profiles.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.user_id;
          opt.textContent = `${p.user_id} (${p.home_currency})`;
          simUserSelect.appendChild(opt);
        });

        if (userProfilesMap[prevVal]) {
          simUserSelect.value = prevVal;
        } else {
          simUserSelect.value = profiles[0].user_id;
        }

        const selectedUser = simUserSelect.value;
        const homeCur = userProfilesMap[selectedUser] || 'USD';
        const curEl = document.getElementById('sim-currency');
        if (curEl && !curEl.value) {
          curEl.value = homeCur;
        }
        updateSimFxPreview();
      }
    }
  } catch (err) {
    console.error('Error loading profiles:', err);
  }
}

function populateUserPickers(reqs) {
  const runwaySelect = document.getElementById('runway-request-select');
  const simUserSelect = document.getElementById('sim-user-id');

  const seenUsers = new Set();
  runwaySelect.innerHTML = '';

  reqs.forEach(r => {
    runwaySelect.innerHTML += `<option value="${r.request_id}">${r.request_id} (${r.user_id} — ${r.category} ${r.requested_currency} ${r.requested_amount})</option>`;
    if (!seenUsers.has(r.user_id)) {
      seenUsers.add(r.user_id);
      userProfilesMap[r.user_id] = r.home_currency;
      // Only append to simUserSelect if it hasn't been populated with all 275 profiles yet
      if (simUserSelect && simUserSelect.options.length < 10) {
        simUserSelect.innerHTML += `<option value="${r.user_id}">${r.user_id} (${r.home_currency})</option>`;
      }
    }
  });

  runwaySelect.addEventListener('change', () => loadRunwayDetail(runwaySelect.value));
  if (reqs.length > 0) {
    loadRunwayDetail(reqs[0].request_id);
  }

  if (simUserSelect) {
    simUserSelect.addEventListener('change', () => {
      const uid = simUserSelect.value;
      const homeCur = userProfilesMap[uid] || 'USD';
      document.getElementById('sim-currency').value = homeCur;
      updateSimFxPreview();
    });
  }

  const amtEl = document.getElementById('sim-amount');
  const curEl = document.getElementById('sim-currency');
  if (amtEl) amtEl.addEventListener('input', updateSimFxPreview);
  if (curEl) curEl.addEventListener('change', updateSimFxPreview);
}

async function loadRunwayDetail(reqId) {
  try {
    const res = await fetch(`/api/requests/${reqId}`);
    const data = await res.json();
    const req = data.request;
    const fc = data.forecast;

    document.getElementById('strip-user-id').textContent = req.user_id;
    document.getElementById('strip-home-currency').textContent = req.home_currency;
    document.getElementById('strip-start-balance').textContent = `${req.home_currency} ${req.current_available_balance.toLocaleString()}`;
    document.getElementById('strip-min-reserve').textContent = `${req.home_currency} ${req.minimum_balance_to_keep.toLocaleString()}`;
    
    if (fc) {
      document.getElementById('strip-lowest-balance').textContent = `${req.home_currency} ${fc.min_future.toLocaleString()}`;
      document.getElementById('strip-safe-today').textContent = `${req.home_currency} ${fc.amount_safe_today.toLocaleString()}`;

      renderSvgChart('runway-svg', fc.timeline, fc.min_balance);

      // Events table
      const evTbody = document.getElementById('events-table-body');
      evTbody.innerHTML = '';
      fc.events.forEach(ev => {
        const tr = document.createElement('tr');
        const isCredit = ev.is_credit;
        tr.innerHTML = `
          <td>${ev.date}</td>
          <td><span class="badge ${isCredit ? 'badge-emerald' : 'badge-amber'}">${isCredit ? 'Income / Credit' : 'Expense / Debit'}</span></td>
          <td>${ev.category}</td>
          <td>${ev.label}</td>
          <td><strong style="color: ${isCredit ? 'var(--emerald)' : 'var(--text-primary)'};">${isCredit ? '+' : ''}${req.home_currency} ${ev.home_amount.toLocaleString()}</strong></td>
        `;
        evTbody.appendChild(tr);
      });
    }

  } catch (err) {
    console.error('Error loading runway detail:', err);
  }
}

function renderSvgChart(svgId, timeline, minReserve) {
  const svg = document.getElementById(svgId);
  if (!svg || !timeline || timeline.length === 0) return;

  const vb = svg.viewBox && svg.viewBox.baseVal ? svg.viewBox.baseVal : { width: 800, height: 230 };
  const width = vb.width || 800;
  const height = vb.height || 230;
  const padTop = 20;
  const padBottom = 30;
  const padLeft = 65;
  const padRight = 30;

  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const balances = timeline.map(t => t.balance);
  let minVal = Math.min(...balances, minReserve);
  let maxVal = Math.max(...balances, minReserve);
  const buffer = (maxVal - minVal) * 0.1 || 1000;
  minVal = Math.max(0, minVal - buffer);
  maxVal = maxVal + buffer;

  const scaleX = (d) => padLeft + (d / (timeline.length - 1)) * plotW;
  const scaleY = (v) => padTop + plotH - ((v - minVal) / (maxVal - minVal)) * plotH;

  // Build SVG path
  let pathD = '';
  timeline.forEach((pt, idx) => {
    const x = scaleX(idx);
    const y = scaleY(pt.balance);
    pathD += (idx === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`);
  });

  const reserveY = scaleY(minReserve);

  let gridLines = '';
  // Horizontal grid lines
  for (let i = 0; i <= 4; i++) {
    const v = minVal + (i / 4) * (maxVal - minVal);
    const y = scaleY(v);
    gridLines += `
      <line x1="${padLeft}" y1="${y}" x2="${width - padRight}" y2="${y}" stroke="var(--border-subtle)" stroke-width="1" />
      <text x="${padLeft - 8}" y="${y + 4}" fill="var(--text-muted)" font-size="10" text-anchor="end" font-family="var(--font-mono)">${Math.round(v).toLocaleString()}</text>
    `;
  }

  // Day milestones (Day 0, Day 30, Day 60, Day 90)
  [0, 30, 60, 90].forEach(d => {
    if (d < timeline.length) {
      const x = scaleX(d);
      gridLines += `
        <line x1="${x}" y1="${padTop}" x2="${x}" y2="${height - padBottom}" stroke="var(--border-subtle)" stroke-dasharray="3,3" stroke-width="1" />
        <text x="${x}" y="${height - padBottom + 16}" fill="var(--text-muted)" font-size="10" text-anchor="middle" font-family="var(--font-mono)">Day ${d}</text>
      `;
    }
  });

  svg.innerHTML = `
    ${gridLines}
    <!-- Minimum Reserve Line -->
    <line x1="${padLeft}" y1="${reserveY}" x2="${width - padRight}" y2="${reserveY}" stroke="var(--rose)" stroke-width="2" stroke-dasharray="5,5" />
    <text x="${width - padRight}" y="${reserveY - 6}" fill="var(--rose)" font-size="10" text-anchor="end" font-weight="bold">Min Reserve (${Math.round(minReserve).toLocaleString()})</text>
    
    <!-- Balance Curve -->
    <path d="${pathD}" fill="none" stroke="var(--cyan)" stroke-width="2.5" />
    
    <!-- Scrubber Overlay Elements -->
    <line id="${svgId}-scrubber-line" x1="0" y1="${padTop}" x2="0" y2="${height - padBottom}" stroke="white" stroke-width="1" opacity="0" />
    <circle id="${svgId}-scrubber-dot" cx="0" cy="0" r="4" fill="var(--cyan)" stroke="white" stroke-width="1.5" opacity="0" />
  `;

  // Attach mouse hover scrubber
  svg.onmousemove = (e) => {
    const rect = svg.getBoundingClientRect();
    const mouseX = ((e.clientX - rect.left) / rect.width) * width;
    if (mouseX >= padLeft && mouseX <= width - padRight) {
      const ratio = (mouseX - padLeft) / plotW;
      const dayIdx = Math.min(timeline.length - 1, Math.max(0, Math.round(ratio * (timeline.length - 1))));
      const pt = timeline[dayIdx];
      const cx = scaleX(dayIdx);
      const cy = scaleY(pt.balance);

      const scrubberLine = document.getElementById(`${svgId}-scrubber-line`);
      const scrubberDot = document.getElementById(`${svgId}-scrubber-dot`);
      if (scrubberLine && scrubberDot) {
        scrubberLine.setAttribute('x1', cx);
        scrubberLine.setAttribute('x2', cx);
        scrubberLine.setAttribute('opacity', '0.6');
        scrubberDot.setAttribute('cx', cx);
        scrubberDot.setAttribute('cy', cy);
        scrubberDot.setAttribute('opacity', '1');
      }

      const infoBox = document.getElementById('chart-scrubber-info');
      if (infoBox && svgId === 'runway-svg') {
        const headroom = pt.balance - minReserve;
        infoBox.textContent = `Day ${pt.day} (${pt.date}): Balance ${pt.balance.toLocaleString()} (Headroom: ${headroom >= 0 ? '+' : ''}${headroom.toLocaleString()})`;
      }
    }
  };

  svg.onmouseleave = () => {
    const scrubberLine = document.getElementById(`${svgId}-scrubber-line`);
    const scrubberDot = document.getElementById(`${svgId}-scrubber-dot`);
    if (scrubberLine) scrubberLine.setAttribute('opacity', '0');
    if (scrubberDot) scrubberDot.setAttribute('opacity', '0');
    const infoBox = document.getElementById('chart-scrubber-info');
    if (infoBox && svgId === 'runway-svg') {
      infoBox.textContent = 'Hover over chart to scrub days';
    }
  };
}

// --------------------------------------------------------------------------
// What-If Simulation
// --------------------------------------------------------------------------
function updateSimFxPreview() {
  const simUserSelect = document.getElementById('sim-user-id');
  const userId = simUserSelect ? simUserSelect.value : '';
  const homeCur = userProfilesMap[userId] || 'USD';
  const reqCur = document.getElementById('sim-currency').value;
  const amount = parseFloat(document.getElementById('sim-amount').value) || 0;
  const fxRow = document.getElementById('sim-fx-row');
  const fxText = document.getElementById('sim-fx-preview-text');

  if (!fxRow || !fxText) return;

  if (reqCur !== homeCur && amount > 0) {
    const rateKey = `${reqCur}_${homeCur}`;
    const rate = ratesMap[rateKey];
    if (rate) {
      const converted = (amount * rate).toLocaleString(undefined, { maximumFractionDigits: 2 });
      fxText.textContent = `${amount.toLocaleString()} ${reqCur} ≈ ${homeCur} ${converted} (Exchange Rate: 1 ${reqCur} = ${rate.toLocaleString()} ${homeCur})`;
    } else {
      fxText.textContent = `Foreign currency selected. Cross-currency engine converts to ${homeCur} on execution.`;
    }
    fxRow.style.display = 'block';
  } else {
    fxRow.style.display = 'none';
  }
}

function loadSimPreset(userId, amount, cur, cat) {
  const simUserSelect = document.getElementById('sim-user-id');
  if (simUserSelect) {
    let found = false;
    for (let i = 0; i < simUserSelect.options.length; i++) {
      if (simUserSelect.options[i].value === userId) {
        found = true;
        simUserSelect.selectedIndex = i;
        break;
      }
    }
    if (!found) {
      const homeCur = userProfilesMap[userId] || cur || 'USD';
      const opt = document.createElement('option');
      opt.value = userId;
      opt.textContent = `${userId} (${homeCur})`;
      simUserSelect.appendChild(opt);
      simUserSelect.value = userId;
    }
  }
  const amtInput = document.getElementById('sim-amount');
  if (amtInput) amtInput.value = amount;
  const curInput = document.getElementById('sim-currency');
  if (curInput) curInput.value = cur;
  const catInput = document.getElementById('sim-category');
  if (catInput) catInput.value = cat;

  updateSimFxPreview();
  executeSimulation();
}

async function executeSimulation() {
  const simUserSelect = document.getElementById('sim-user-id');
  const userId = simUserSelect ? simUserSelect.value.trim() : '';
  const btn = document.getElementById('btn-run-simulation');

  if (!userId) {
    showToast('Please select a valid User ID', 'amber', '⚠');
    return;
  }

  const reqDate = document.getElementById('sim-request-date').value;
  const amount = parseFloat(document.getElementById('sim-amount').value);
  const currency = document.getElementById('sim-currency').value;
  const category = document.getElementById('sim-category').value;
  const completionDate = document.getElementById('sim-completion-date').value;
  const desc = document.getElementById('sim-desc').value;
  const partial = document.getElementById('sim-partial').checked;

  if (isNaN(amount) || amount <= 0) {
    showToast('Please enter a valid amount greater than 0', 'amber', '⚠');
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span>Scoring Scenario...</span>';

  try {
    const res = await fetch('/api/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        request_date: reqDate,
        requested_amount: amount,
        requested_currency: currency,
        category: category,
        item_description: desc,
        desired_completion_date: completionDate,
        allows_partial_payment: partial
      })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Simulation error');

    document.getElementById('sim-placeholder').style.display = 'none';
    document.getElementById('sim-live-content').style.display = 'block';

    const dec = data.decision;
    const homeCur = data.user_profile.home_currency;
    const stBadge = document.getElementById('sim-result-status-badge');
    const st = dec.affordability_status;
    stBadge.textContent = st.replace(/_/g, ' ').toUpperCase();
    stBadge.className = 'status-badge-lg';
    const colorMap = {
      affordable_now: { color: 'var(--emerald)', bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.35)' },
      affordable_with_plan: { color: 'var(--cyan)', bg: 'rgba(6,182,212,0.12)', border: 'rgba(6,182,212,0.35)' },
      affordable_later: { color: 'var(--amber)', bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.35)' },
      not_affordable: { color: 'var(--rose)', bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.35)' }
    };
    const cm = colorMap[st] || colorMap.not_affordable;
    stBadge.style.color = cm.color;
    stBadge.style.background = cm.bg;
    stBadge.style.borderColor = cm.border;

    // Toast feedback for decision
    const toastMsgs = {
      affordable_now: ['Affordable Now — safe to proceed today', 'emerald', '✓'],
      affordable_with_plan: ['Affordable With Plan — installments available', 'cyan', '●'],
      affordable_later: ['Affordable Later — wait recommended', 'amber', '◉'],
      not_affordable: ['Not Affordable — reserve breach risk', 'rose', '✕']
    };
    const [tm, tt, ti] = toastMsgs[st] || ['Decision computed', 'cyan', '✦'];
    showToast(tm, tt, ti);

    // 1. Cross-Currency Conversion Banner
    const fxBanner = document.getElementById('sim-result-fx-banner');
    if (data.conversion && data.conversion.is_cross_currency) {
      document.getElementById('sim-result-fx-calc').textContent = data.conversion.display_text;
      document.getElementById('sim-result-fx-rate').textContent = `Exchange Rate: 1 ${data.conversion.requested_currency} = ${data.conversion.exchange_rate.toLocaleString()} ${data.conversion.home_currency}`;
      fxBanner.style.display = 'block';
    } else {
      fxBanner.style.display = 'none';
    }

    // 2. Safe-to-Pay Limit Today Context Subtext
    const contextSub = document.getElementById('sim-result-context-sub');
    const safeAmt = Number(dec.amount_safe_to_pay);  // API returns string, parse to Number for comma formatting
    const fmtNum = (n) => Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const evalAmt = (data.conversion && data.conversion.is_cross_currency)
      ? data.conversion.converted_amount
      : amount;

    if (st === 'not_affordable') {
      const shortfall = Math.max(0, evalAmt - safeAmt);
      contextSub.innerHTML = `<span style="color: var(--rose);">Safe Limit: ${homeCur} ${fmtNum(safeAmt)} &lt; Requested: ${homeCur} ${fmtNum(evalAmt)} (Shortfall: ${homeCur} ${fmtNum(shortfall)})</span>`;
    } else if (st === 'affordable_now') {
      contextSub.innerHTML = `<span style="color: var(--emerald);">Requested ${homeCur} ${fmtNum(evalAmt)} is 100% within today's safe limit.</span>`;
    } else if (st === 'affordable_with_plan') {
      contextSub.innerHTML = `<span style="color: var(--cyan);">Safe limit today is ${homeCur} ${fmtNum(safeAmt)} — purchase requires installment plan.</span>`;
    } else {
      contextSub.innerHTML = `<span style="color: var(--amber);">Safe limit today is ${homeCur} ${fmtNum(safeAmt)} — liquidity safe on earliest date.</span>`;
    }

    const toTitleCase = (str) => str ? str.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : '';

    document.getElementById('sim-result-safe-amount').textContent = `${homeCur} ${fmtNum(safeAmt)}`;
    document.getElementById('sim-result-explanation').textContent = dec.decision_explanation;
    document.getElementById('sim-result-method').innerHTML = getMethodBadge(dec.recommended_payment_method);
    const planVal = dec.payment_plan && dec.payment_plan !== 'none' ? dec.payment_plan : '<span style="color: var(--text-muted);">None</span>';
    document.getElementById('sim-result-plan').innerHTML = planVal;
    document.getElementById('sim-result-earliest-date').textContent = dec.earliest_date_for_full_payment || 'None';
    const changesVal = dec.spending_changes_needed && dec.spending_changes_needed !== 'none' ? dec.spending_changes_needed : 'None required';    
    document.getElementById('sim-result-changes').textContent = changesVal;

    // 3. Render enlarged chart and 3 actionable metrics
    if (data.timeline && data.timeline.timeline) {
      renderSvgChart('sim-runway-svg', data.timeline.timeline, data.timeline.min_balance);

      const fmtM = (n) => Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      document.getElementById('sim-metric-min-balance').textContent = `${homeCur} ${fmtM(data.timeline.min_projected_balance)}`;
      
      const breachEl = document.getElementById('sim-metric-breach');
      const breachSub = document.getElementById('sim-metric-breach-sub');
      if (data.timeline.first_breach_day) {
        breachEl.innerHTML = `<span style="color: var(--rose);">Day ${data.timeline.first_breach_day.day} (${data.timeline.first_breach_day.date})</span>`;
        breachSub.textContent = `Breaches reserve by ${homeCur} ${fmtM(data.timeline.first_breach_day.breach_amount)}`;
      } else {
        breachEl.innerHTML = `<span style="color: var(--emerald);">No Breach (Safe Runway)</span>`;
        breachSub.textContent = `Maintains policy reserve throughout 90 days`;
      }

      document.getElementById('sim-metric-reserve').textContent = `${homeCur} ${fmtM(data.user_profile.minimum_balance_to_keep)}`;
    }

  } catch (err) {
    showToast(`Simulation failed: ${err.message}`, 'rose', '✕');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
      <span>Execute Affordability Engine</span>
    `;
  }
}

// --------------------------------------------------------------------------
// Sample Benchmark
// --------------------------------------------------------------------------
async function loadSamples() {
  try {
    const res = await fetch('/api/samples');
    const data = await res.json();
    allSamples = data.samples;

    // Count live matches / mismatches from actual data
    const matchCount = allSamples.filter(s => s.status_match && s.method_match).length;
    const mismatchCount = allSamples.length - matchCount;

    // Update accuracy badges
    const statusAccBadge = document.getElementById('bench-status-acc');
    const methodAccBadge = document.getElementById('bench-method-acc');
    if (statusAccBadge) statusAccBadge.textContent = `Status Accuracy: ${data.status_accuracy_pct}%`;
    if (methodAccBadge) methodAccBadge.textContent = `Method Accuracy: ${data.method_accuracy_pct}%`;

    // Update chip labels dynamically with live counts
    const allChip = document.getElementById('chip-bench-all') || document.querySelector('#view-benchmark .chip[onclick*="\'all\'"]');
    const matchChip = document.getElementById('chip-bench-matches') || document.querySelector('#view-benchmark .chip[onclick*="\'matches\'"]');
    const mismatchChip = document.getElementById('chip-bench-mismatches') || document.querySelector('#view-benchmark .chip[onclick*="\'mismatches\'"]');
    if (allChip)      allChip.textContent      = `All Samples (${allSamples.length})`;
    if (matchChip)    matchChip.textContent    = `Matches (${matchCount})`;
    if (mismatchChip) mismatchChip.textContent = `Residual Mismatches (${mismatchCount})`;

    // Update currency filter chip counts
    const benchCurrencies = ['ZAR', 'IDR', 'INR', 'EUR', 'USD'];
    benchCurrencies.forEach(cur => {
      const cnt = allSamples.filter(s => s.requested_currency === cur).length;
      const chipEl = document.getElementById(`chip-bench-cur-${cur.toLowerCase()}`);
      if (chipEl) chipEl.textContent = `${cur} (${cnt})`;
    });

    renderBenchmarkTable(allSamples);

  } catch (err) {
    console.error('Error loading samples:', err);
  }
}

function filterBenchmark(mode, btn) {
  sampleBenchmarkFilter = mode;
  // Reset only the result-filter chips (not currency chips)
  ['chip-bench-all', 'chip-bench-matches', 'chip-bench-mismatches'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  });
  if (btn) btn.classList.add('active');
  applyBenchmarkFilters();
}

function filterBenchmarkByCurrency(currency, btn) {
  benchmarkCurrencyFilter = currency;
  // Reset only the currency-filter chips
  ['chip-bench-cur-all', 'chip-bench-cur-zar', 'chip-bench-cur-idr', 'chip-bench-cur-inr', 'chip-bench-cur-eur', 'chip-bench-cur-usd'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  });
  if (btn) btn.classList.add('active');
  applyBenchmarkFilters();
}

function applyBenchmarkFilters() {
  let filtered = allSamples;

  // Apply status filter
  if (sampleBenchmarkFilter === 'matches') {
    filtered = filtered.filter(s => s.status_match && s.method_match);
  } else if (sampleBenchmarkFilter === 'mismatches') {
    filtered = filtered.filter(s => !s.status_match || !s.method_match);
  }

  // Apply currency filter
  if (benchmarkCurrencyFilter !== 'all') {
    filtered = filtered.filter(s => s.requested_currency === benchmarkCurrencyFilter);
  }

  renderBenchmarkTable(filtered);
}

function renderBenchmarkTable(samples) {
  const tbody = document.getElementById('benchmark-table-body');
  tbody.innerHTML = '';

  if (!samples || samples.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:32px;">No samples in this filter</td></tr>`;
    return;
  }

  samples.forEach(s => {
    const tr = document.createElement('tr');
    const matched = s.status_match && s.method_match;
    const fmtAmt = Number(s.requested_amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    tr.innerHTML = `
      <td><strong class="font-mono text-cyan">${s.request_id}</strong></td>
      <td><span class="font-mono">${s.user_id}</span></td>
      <td class="font-mono">${s.requested_currency} ${fmtAmt}</td>
      <td>${getStatusBadge(s.expected_status)}</td>
      <td>${getStatusBadge(s.predicted_status)}</td>
      <td>${getMethodBadge(s.expected_method)}</td>
      <td>${getMethodBadge(s.predicted_method)}</td>
      <td>
        <span class="badge ${matched ? 'badge-emerald' : 'badge-rose'}">
          ${matched ? '✓ Exact Match' : '✗ Residual Mismatch'}
        </span>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// --------------------------------------------------------------------------
// Currency Matrix & Converter
// --------------------------------------------------------------------------
let allRates = [];
let currentRateFilter = 'all';

async function loadRates() {
  try {
    const res = await fetch('/api/rates');
    const data = await res.json();
    allRates = data.rates || [];

    allRates.forEach(r => {
      ratesMap[`${r.from_currency}_${r.to_currency}`] = r.rate;
    });

    // Dynamically update chip counts
    const allCount = allRates.length;
    const chipAll = document.getElementById('chip-rates-all');
    if (chipAll) chipAll.textContent = `All (${allCount})`;
    const currencies = ['ZAR', 'USD', 'EUR', 'INR', 'IDR'];
    currencies.forEach(cur => {
      const cnt = allRates.filter(r => r.from_currency === cur || r.to_currency === cur).length;
      const chipEl = document.getElementById(`chip-rates-${cur.toLowerCase()}`);
      if (chipEl) chipEl.textContent = `${cur} (${cnt})`;
    });
    const countTag = document.getElementById('rates-count-tag');
    if (countTag) countTag.textContent = `${allCount} Graph Pairs`;

    // Also update benchmark currency chip counts after samples loaded
    // This is done in loadSamples after allSamples is set

    renderRatesTable(allRates);

    // Attach reactive input/change listeners if not already present
    const amtInput = document.getElementById('convert-amount');
    const fromSelect = document.getElementById('convert-from');
    const toSelect = document.getElementById('convert-to');
    
    if (amtInput) amtInput.addEventListener('input', executeCurrencyConversion);
    if (fromSelect) fromSelect.addEventListener('change', executeCurrencyConversion);
    if (toSelect) toSelect.addEventListener('change', executeCurrencyConversion);

    executeCurrencyConversion();
    updateSimFxPreview();

  } catch (err) {
    console.error('Error loading rates:', err);
  }
}

function renderRatesTable(rates) {
  const tbody = document.getElementById('rates-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  if (!rates || rates.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:24px;">No rate pairs found for this filter</td></tr>`;
    return;
  }

  rates.forEach(r => {
    const tr = document.createElement('tr');
    tr.style.cursor = 'pointer';
    tr.title = `Click to convert ${r.from_currency} → ${r.to_currency}`;
    const badgeHtml = r.is_direct 
      ? `<span class="badge badge-emerald" style="font-size: 10px; padding: 2px 6px;">Direct Pair</span>` 
      : `<span class="badge badge-purple" style="font-size: 10px; padding: 2px 6px;">BFS Multi-Hop</span>`;

    tr.innerHTML = `
      <td><strong class="text-cyan">${r.from_currency}</strong></td>
      <td><strong class="text-emerald">${r.to_currency}</strong></td>
      <td class="font-mono">${r.rate}</td>
      <td>${badgeHtml}</td>
    `;
    tr.addEventListener('click', () => {
      document.getElementById('convert-from').value = r.from_currency;
      document.getElementById('convert-to').value = r.to_currency;
      recalculateCurrencyManual();
    });
    tbody.appendChild(tr);
  });
}

function filterRates(currency, btn) {
  currentRateFilter = currency;
  const chipContainer = document.getElementById('rates-filter-chips');
  if (chipContainer) {
    chipContainer.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  }
  if (btn) btn.classList.add('active');

  let filtered = allRates;
  if (currency !== 'all') {
    filtered = allRates.filter(r => r.from_currency === currency || r.to_currency === currency);
  }
  renderRatesTable(filtered);
  const tag = document.getElementById('rates-count-tag');
  if (tag) tag.textContent = `${filtered.length} Graph Pairs`;
}

function swapCurrencies() {
  const fromSelect = document.getElementById('convert-from');
  const toSelect = document.getElementById('convert-to');
  if (!fromSelect || !toSelect) return;
  const prevFrom = fromSelect.value;
  fromSelect.value = toSelect.value;
  toSelect.value = prevFrom;
  showToast(`Swapped: ${fromSelect.value} ⇄ ${toSelect.value}`, 'cyan', '⇄');
  recalculateCurrencyManual();
}

function setConvertAmount(val) {
  const amtInput = document.getElementById('convert-amount');
  if (amtInput) {
    amtInput.value = val;
    document.querySelectorAll('.quick-chips .chip').forEach(c => {
      c.classList.toggle('active', c.textContent.replace(/,/g, '').trim() === String(val));
    });
    recalculateCurrencyManual();
  }
}

async function recalculateCurrencyManual() {
  const btn = document.getElementById('btn-recalculate-convert');
  const icon = document.getElementById('recalc-btn-icon');
  const text = document.getElementById('recalc-btn-text');
  const resultBox = document.getElementById('conversion-result-box');

  if (btn) {
    btn.disabled = true;
    if (icon) icon.classList.add('spin-icon');
    if (text) text.textContent = 'Recalculating...';
  }

  // Trigger pulse glow animation on result box
  if (resultBox) {
    resultBox.classList.remove('recalculated');
    void resultBox.offsetWidth; // trigger reflow
    resultBox.classList.add('recalculated');
  }

  try {
    const res = await executeCurrencyConversion(true);
    if (res && res.success) {
      showToast(`Recalculated: ${res.from} ${res.amountFormatted} = ${res.to} ${res.convertedFormatted}`, 'cyan', '💱');
    }
  } catch (err) {
    console.error('Manual recalculation error:', err);
  } finally {
    setTimeout(() => {
      if (btn) btn.disabled = false;
      if (icon) icon.classList.remove('spin-icon');
      if (text) text.textContent = 'Recalculate Now';
      if (resultBox) resultBox.classList.remove('recalculated');
    }, 450);
  }
}

async function executeCurrencyConversion(isManual = false) {
  const amtInput = document.getElementById('convert-amount');
  const fromSelect = document.getElementById('convert-from');
  const toSelect = document.getElementById('convert-to');
  const dispVal = document.getElementById('conv-display-value');
  const dispRate = document.getElementById('conv-display-rate');

  if (!amtInput || !fromSelect || !toSelect || !dispVal) return { success: false };

  const amount = parseFloat(amtInput.value);
  const from = fromSelect.value;
  const to = toSelect.value;

  if (isNaN(amount) || amount <= 0) {
    dispVal.textContent = `${to} 0.00`;
    dispRate.textContent = `Enter a valid amount above 0`;
    if (isManual) {
      showToast('Please enter an amount greater than 0', 'amber', '⚠');
    }
    return { success: false };
  }

  // Exact 1:1 match if both currencies are identical (e.g. USD -> USD)
  if (from === to) {
    const exactFormatted = amount.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
    dispVal.textContent = `${to} ${exactFormatted}`;
    dispRate.textContent = `1 ${from} = 1.000000 ${to} (Same Currency — 100% Parity)`;
    return {
      success: true,
      from,
      to,
      amount,
      amountFormatted: amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
      convertedFormatted: exactFormatted,
      rate: 1.0
    };
  }

  try {
    const res = await fetch(`/api/convert?amount=${amount}&from_currency=${from}&to_currency=${to}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Conversion calculation failed');

    const formattedConverted = Number(data.converted_amount).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
    dispVal.textContent = `${to} ${formattedConverted}`;
    dispRate.textContent = `1 ${from} = ${Number(data.rate).toLocaleString(undefined, { maximumFractionDigits: 6 })} ${to}`;

    return {
      success: true,
      from,
      to,
      amount,
      amountFormatted: amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
      convertedFormatted: formattedConverted,
      rate: data.rate
    };
  } catch (err) {
    // Check in-memory ratesMap fallback
    const directKey = `${from}_${to}`;
    if (ratesMap && ratesMap[directKey]) {
      const localRate = ratesMap[directKey];
      const localConverted = (amount * localRate).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      });
      dispVal.textContent = `${to} ${localConverted}`;
      dispRate.textContent = `1 ${from} = ${Number(localRate).toLocaleString(undefined, { maximumFractionDigits: 6 })} ${to}`;
      return {
        success: true,
        from,
        to,
        amount,
        amountFormatted: amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        convertedFormatted: localConverted,
        rate: localRate
      };
    }

    dispVal.textContent = 'Conversion Error';
    dispRate.textContent = err.message;
    if (isManual) {
      showToast(`Conversion failed: ${err.message}`, 'rose', '✕');
    }
    return { success: false };
  }
}

// --------------------------------------------------------------------------
// Universal Command Palette (Ctrl+K)
// --------------------------------------------------------------------------
function openSearch() {
  const p = document.getElementById('search-palette');
  p.classList.add('active');
  const input = document.getElementById('palette-search-input');
  input.value = '';
  input.focus();
  handlePaletteSearch('');
}

function closeSearchPalette(e) {
  const p = document.getElementById('search-palette');
  if (p) p.classList.remove('active');
}

function handlePaletteSearch(q) {
  const container = document.getElementById('palette-results');
  container.innerHTML = '';
  const query = q.toLowerCase().trim();

  // Navigation options
  const navShortcuts = [
    { title: 'Executive Overview', desc: 'Holistic KPI deck and distribution', tab: 'overview' },
    { title: 'Decision Explorer', desc: 'Browse all 250 requests', tab: 'explorer' },
    { title: '90-Day Cash Runway', desc: 'Daily liquidity & reserve waterline chart', tab: 'runway' },
    { title: 'What-If Purchase Simulator', desc: 'Run live scenario evaluation', tab: 'simulator' },
    { title: 'Sample Benchmark', desc: '25 organizer test cases', tab: 'benchmark' },
    { title: 'Currency Matrix', desc: 'Multi-hop shortest path exchange converter', tab: 'rates' },
    { title: 'Audit & Deliverables', desc: 'Download output.csv & view zero token report', tab: 'audit' },
  ];

  const matchingNav = navShortcuts.filter(n => !query || n.title.toLowerCase().includes(query));
  matchingNav.forEach(n => {
    const item = document.createElement('div');
    item.className = 'palette-item';
    item.innerHTML = `
      <div class="palette-item-left">
        <div class="export-icon" style="width: 28px; height: 28px; font-size: 10px;">TAB</div>
        <div>
          <div class="palette-item-title">${n.title}</div>
          <div class="palette-item-sub">${n.desc}</div>
        </div>
      </div>
      <span class="nav-badge">Jump</span>
    `;
    item.onclick = () => {
      switchTab(n.tab);
      closeSearchPalette();
    };
    container.appendChild(item);
  });

  // Matching requests
  if (query && allRequests.length > 0) {
    const matchingReqs = allRequests.filter(r => 
      r.request_id.toLowerCase().includes(query) ||
      r.user_id.toLowerCase().includes(query) ||
      r.category.toLowerCase().includes(query)
    ).slice(0, 8);

    matchingReqs.forEach(r => {
      const item = document.createElement('div');
      item.className = 'palette-item';
      item.innerHTML = `
        <div class="palette-item-left">
          <div class="export-icon" style="width: 28px; height: 28px; font-size: 9px; background: rgba(16, 185, 129, 0.2); color: var(--emerald);">REQ</div>
          <div>
            <div class="palette-item-title">${r.request_id} · ${r.requested_currency} ${r.requested_amount.toLocaleString()}</div>
            <div class="palette-item-sub">${r.user_id} — ${r.affordability_status}</div>
          </div>
        </div>
        <span class="nav-badge">Inspect</span>
      `;
      item.onclick = () => {
        closeSearchPalette();
        inspectRequest(r.request_id);
      };
      container.appendChild(item);
    });
  }
}
