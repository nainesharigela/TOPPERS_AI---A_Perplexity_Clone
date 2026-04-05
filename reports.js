/**
 * Reports & Alerts UI — reports.js
 * Handles the reports timeline, schedule management, and report detail views
 */
(function () {

    const schedulesListEl = document.getElementById('schedules-list');
    const schedulesEmpty = document.getElementById('schedules-empty');
    const reportsTimeline = document.getElementById('reports-timeline');
    const reportsEmpty = document.getElementById('reports-empty');
    const reportModal = document.getElementById('report-detail-modal');
    const reportTitle = document.getElementById('report-detail-title');
    const reportBody = document.getElementById('report-detail-body');
    const closeReportBtn = document.getElementById('close-report-detail');

    async function apiFetch(url, opts = {}) {
        const base = window.API_BASE || '';
        const resp = await fetch(`${base}${url}`, {
            headers: { 'Content-Type': 'application/json' },
            ...opts,
            body: opts.body ? JSON.stringify(opts.body) : undefined
        });
        return resp.json();
    }

    // --- Load Schedules ---
    window.loadReports = async function () {
        await loadSchedules();
        await loadReportList();
    };

    async function loadSchedules() {
        try {
            const data = await apiFetch('/api/bi/schedules');
            const scheds = data.schedules || [];

            if (scheds.length === 0) {
                schedulesEmpty.classList.remove('hidden');
                // Only keep the empty message
                const existing = schedulesListEl.querySelectorAll('.schedule-card');
                existing.forEach(el => el.remove());
                return;
            }

            schedulesEmpty.classList.add('hidden');
            // Remove old cards
            const existing = schedulesListEl.querySelectorAll('.schedule-card');
            existing.forEach(el => el.remove());

            scheds.forEach(s => {
                const card = document.createElement('div');
                card.className = 'schedule-card';

                const freqIcon = s.frequency === 'daily' ? 'fa-sun' : 'fa-calendar-week';
                const statusClass = s.active ? 'active' : 'paused';
                const lastRun = s.last_run ? formatDate(s.last_run) : 'Never';
                const nextRun = s.next_run ? formatDate(s.next_run) : '—';

                card.innerHTML = `
                    <div class="schedule-card-left">
                        <div class="schedule-icon ${statusClass}"><i class="fa-solid ${freqIcon}"></i></div>
                        <div class="schedule-info">
                            <div class="schedule-comp-name">${escapeHtml(s.competitor_name || 'Unknown')}</div>
                            <div class="schedule-comp-url">${escapeHtml(truncateUrl(s.competitor_url))}</div>
                        </div>
                    </div>
                    <div class="schedule-card-right">
                        <div class="schedule-timing">
                            <div><small>Last:</small> ${lastRun}</div>
                            <div><small>Next:</small> ${nextRun}</div>
                        </div>
                        <span class="freq-badge ${s.frequency}">${s.frequency}</span>
                        <button class="remove-schedule-btn" data-id="${s.competitor_id}" title="Remove schedule">
                            <i class="fa-solid fa-trash-can"></i>
                        </button>
                    </div>
                `;

                card.querySelector('.remove-schedule-btn').addEventListener('click', async () => {
                    if (!confirm('Remove this schedule?')) return;
                    try {
                        await apiFetch(`/api/bi/schedule/${s.competitor_id}`, { method: 'DELETE' });
                        loadSchedules();
                    } catch (err) {
                        alert('Failed: ' + err.message);
                    }
                });

                schedulesListEl.appendChild(card);
            });
        } catch (err) {
            console.error('Failed to load schedules:', err);
        }
    }

    // --- Load Reports Timeline ---
    async function loadReportList() {
        try {
            const data = await apiFetch('/api/bi/reports');
            const reports = data.reports || [];

            // Remove old items
            const existing = reportsTimeline.querySelectorAll('.report-card');
            existing.forEach(el => el.remove());

            if (reports.length === 0) {
                reportsEmpty.classList.remove('hidden');
                return;
            }

            reportsEmpty.classList.add('hidden');

            // Group by date
            const groups = {};
            reports.forEach(r => {
                const dateKey = r.created_at ? r.created_at.split('T')[0] : 'Unknown';
                if (!groups[dateKey]) groups[dateKey] = [];
                groups[dateKey].push(r);
            });

            Object.keys(groups).sort().reverse().forEach(dateKey => {
                const dateLabel = document.createElement('div');
                dateLabel.className = 'report-date-label';
                dateLabel.textContent = formatDateLabel(dateKey);
                reportsTimeline.appendChild(dateLabel);

                groups[dateKey].forEach(r => {
                    const card = document.createElement('div');
                    card.className = 'report-card';

                    // Count changes by type
                    const ch = r.changes || {};
                    const badges = [];
                    if ((ch.price_drops || []).length) badges.push(`<span class="rb drop">▼ ${ch.price_drops.length} price drops</span>`);
                    if ((ch.price_increases || []).length) badges.push(`<span class="rb increase">▲ ${ch.price_increases.length} increases</span>`);
                    if ((ch.new_products || []).length) badges.push(`<span class="rb new-product">+ ${ch.new_products.length} new</span>`);
                    if ((ch.removed_products || []).length) badges.push(`<span class="rb removed">- ${ch.removed_products.length} removed</span>`);
                    if ((ch.restocked || []).length) badges.push(`<span class="rb restocked">📦 ${ch.restocked.length} restocked</span>`);
                    if ((ch.out_of_stock || []).length) badges.push(`<span class="rb oos">⚠ ${ch.out_of_stock.length} out of stock</span>`);

                    card.innerHTML = `
                        <div class="report-card-header">
                            <div class="report-comp">${escapeHtml(r.competitor_name || 'Unknown')}</div>
                            <div class="report-time">${formatTime(r.created_at)}</div>
                        </div>
                        <div class="report-summary">${escapeHtml(r.summary)}</div>
                        <div class="report-badges">${badges.join('')}</div>
                    `;

                    card.addEventListener('click', () => openReportDetail(r));
                    reportsTimeline.appendChild(card);
                });
            });
        } catch (err) {
            console.error('Failed to load reports:', err);
        }
    }

    // --- Report Detail ---
    function openReportDetail(report) {
        reportTitle.textContent = report.competitor_name || 'Change Report';
        const ch = report.changes || {};

        let html = `<div class="report-summary-block">${escapeHtml(report.summary)}</div>`;
        html += `<div class="report-time-block">Generated: ${formatDate(report.created_at)}</div>`;

        // Price Drops
        if ((ch.price_drops || []).length) {
            html += `<h4 class="change-section-title drop-title">🔻 Price Drops</h4>`;
            html += `<div class="change-items">`;
            ch.price_drops.forEach(p => {
                const sym = currSymbol(p.currency);
                html += `<div class="change-item drop">
                    <span class="ci-name">${escapeHtml(p.name)}</span>
                    <span class="ci-change">${sym}${p.old_price} → ${sym}${p.price} <em>(−${p.change_pct}%)</em></span>
                </div>`;
            });
            html += `</div>`;
        }

        // Price Increases
        if ((ch.price_increases || []).length) {
            html += `<h4 class="change-section-title inc-title">🔺 Price Increases</h4>`;
            html += `<div class="change-items">`;
            ch.price_increases.forEach(p => {
                const sym = currSymbol(p.currency);
                html += `<div class="change-item increase">
                    <span class="ci-name">${escapeHtml(p.name)}</span>
                    <span class="ci-change">${sym}${p.old_price} → ${sym}${p.price} <em>(+${p.change_pct}%)</em></span>
                </div>`;
            });
            html += `</div>`;
        }

        // New Products
        if ((ch.new_products || []).length) {
            html += `<h4 class="change-section-title new-title">🆕 New Products</h4>`;
            html += `<div class="change-items">`;
            ch.new_products.forEach(p => {
                const sym = currSymbol(p.currency);
                const price = p.price != null ? `${sym}${p.price}` : 'Price N/A';
                html += `<div class="change-item new-prod">
                    <span class="ci-name">${escapeHtml(p.name)}</span>
                    <span class="ci-price">${price}</span>
                </div>`;
            });
            html += `</div>`;
        }

        // Removed
        if ((ch.removed_products || []).length) {
            html += `<h4 class="change-section-title removed-title">❌ Removed Products</h4>`;
            html += `<div class="change-items">`;
            ch.removed_products.forEach(p => {
                html += `<div class="change-item removed"><span class="ci-name">${escapeHtml(p.name)}</span></div>`;
            });
            html += `</div>`;
        }

        // Restocked
        if ((ch.restocked || []).length) {
            html += `<h4 class="change-section-title restock-title">📦 Restocked</h4>`;
            html += `<div class="change-items">`;
            ch.restocked.forEach(p => {
                html += `<div class="change-item restocked"><span class="ci-name">${escapeHtml(p.name)}</span></div>`;
            });
            html += `</div>`;
        }

        reportBody.innerHTML = html;
        reportModal.classList.remove('hidden');
    }

    if (closeReportBtn) {
        closeReportBtn.addEventListener('click', () => reportModal.classList.add('hidden'));
    }
    if (reportModal) {
        reportModal.addEventListener('click', (e) => {
            if (e.target === reportModal) reportModal.classList.add('hidden');
        });
    }

    // --- Utility Functions ---
    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function truncateUrl(url) {
        try {
            return new URL(url).hostname.replace(/^www\./, '');
        } catch { return url ? url.substring(0, 40) : ''; }
    }
    function currSymbol(c) {
        const map = { USD: '$', INR: '₹', EUR: '€', GBP: '£' };
        return map[c] || '$';
    }
    function formatDate(d) {
        if (!d) return '—';
        try {
            return new Date(d + (d.includes('Z') ? '' : 'Z')).toLocaleString();
        } catch { return d; }
    }
    function formatTime(d) {
        if (!d) return '';
        try {
            return new Date(d + (d.includes('Z') ? '' : 'Z')).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch { return ''; }
    }
    function formatDateLabel(dateStr) {
        try {
            const d = new Date(dateStr + 'T00:00:00Z');
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const diff = Math.floor((today - d) / 86400000);
            if (diff === 0) return 'Today';
            if (diff === 1) return 'Yesterday';
            return d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
        } catch { return dateStr; }
    }

})();
