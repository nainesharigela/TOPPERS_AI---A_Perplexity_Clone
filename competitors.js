/**
 * Competitors Tracker UI — competitors.js
 * Handles all competitor tracking, product display, and AI Q&A
 */
(function () {
    const API = window.API_BASE || '';

    // --- DOM Elements ---
    const competitorsView = document.getElementById('competitors-view');
    const urlInput = document.getElementById('competitor-url-input');
    const trackBtn = document.getElementById('track-competitor-btn');
    const biLoading = document.getElementById('bi-loading');
    const biEmpty = document.getElementById('bi-empty-state');
    const cardsGrid = document.getElementById('competitor-cards');
    const detailPanel = document.getElementById('product-detail-panel');
    const backBtn = document.getElementById('back-to-competitors');
    const recrawlBtn = document.getElementById('recrawl-btn');
    const scheduleBtn = document.getElementById('schedule-btn');
    const askAiToggle = document.getElementById('ask-ai-toggle');
    const aiBar = document.getElementById('ai-question-bar');
    const aiInput = document.getElementById('ai-question-input');
    const aiSubmit = document.getElementById('ai-question-submit');
    const aiAnswerBox = document.getElementById('ai-answer-box');
    const productsTbody = document.getElementById('products-tbody');
    const productsEmpty = document.getElementById('products-empty');
    const crawlMeta = document.getElementById('crawl-meta');
    const detailFavicon = document.getElementById('detail-favicon');
    const detailName = document.getElementById('detail-comp-name');
    const loadingText = document.querySelector('.bi-loading-text');

    // Schedule modal elements
    const scheduleModal = document.getElementById('schedule-modal');
    const closeScheduleModal = document.getElementById('close-schedule-modal');
    const saveScheduleBtn = document.getElementById('save-schedule-btn');
    const freqOptions = document.querySelectorAll('.freq-option');

    let currentCompetitorId = null;
    let currentProducts = [];
    let sortField = null;
    let sortAsc = true;

    // --- API Helpers ---
    async function apiFetch(url, opts = {}) {
        const base = window.API_BASE || '';
        const resp = await fetch(`${base}${url}`, {
            headers: { 'Content-Type': 'application/json' },
            ...opts,
            body: opts.body ? JSON.stringify(opts.body) : undefined
        });
        return resp.json();
    }

    // --- Track New Competitor ---
    if (trackBtn) {
        trackBtn.addEventListener('click', () => trackCompetitor());
    }
    if (urlInput) {
        urlInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') trackCompetitor();
        });
    }

    async function trackCompetitor() {
        const input = urlInput.value.trim();
        if (!input) return;

        // Show loading
        biLoading.classList.remove('hidden');
        biEmpty.classList.add('hidden');
        cardsGrid.classList.add('hidden');
        detailPanel.classList.add('hidden');
        trackBtn.disabled = true;
        loadingText.textContent = 'Crawling competitor site...';

        try {
            const isUrl = input.includes('.') || input.startsWith('http');
            const body = isUrl ? { url: input } : { brand: input };

            const data = await apiFetch('/api/bi/track', { method: 'POST', body });

            if (data.error) {
                alert('Error: ' + data.error);
                biLoading.classList.add('hidden');
                biEmpty.classList.remove('hidden');
                return;
            }

            urlInput.value = '';
            biLoading.classList.add('hidden');

            // Show the detail panel directly for the new competitor
            showCompetitorDetail(data.competitor, data.products, null);

        } catch (err) {
            alert('Failed to track competitor: ' + err.message);
            biLoading.classList.add('hidden');
            biEmpty.classList.remove('hidden');
        } finally {
            trackBtn.disabled = false;
        }
    }

    // --- Load All Competitors ---
    window.loadCompetitors = async function () {
        try {
            const data = await apiFetch('/api/bi/competitors');
            const comps = data.competitors || [];

            if (comps.length === 0) {
                biEmpty.classList.remove('hidden');
                cardsGrid.classList.add('hidden');
                return;
            }

            biEmpty.classList.add('hidden');
            cardsGrid.classList.remove('hidden');
            detailPanel.classList.add('hidden');
            renderCompetitorCards(comps);
        } catch (err) {
            console.error('Failed to load competitors:', err);
        }
    };

    function renderCompetitorCards(competitors) {
        cardsGrid.innerHTML = '';
        competitors.forEach(comp => {
            const card = document.createElement('div');
            card.className = 'competitor-card';
            card.dataset.id = comp.id;

            const schedBadge = comp.frequency
                ? `<span class="sched-badge"><i class="fa-regular fa-clock"></i> ${comp.frequency}</span>`
                : '';

            const lastCrawl = comp.last_crawled_at
                ? timeAgo(comp.last_crawled_at)
                : 'Never';

            card.innerHTML = `
                <div class="comp-card-header">
                    <img src="${comp.favicon_url || ''}" alt="" class="comp-favicon" onerror="this.style.display='none'">
                    <div class="comp-card-info">
                        <div class="comp-card-name">${escapeHtml(comp.name || 'Unknown')}</div>
                        <div class="comp-card-url">${escapeHtml(truncateUrl(comp.url))}</div>
                    </div>
                    <button class="comp-delete-btn" data-id="${comp.id}" title="Remove">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
                <div class="comp-card-stats">
                    <div class="comp-stat">
                        <span class="comp-stat-value">${comp.product_count || 0}</span>
                        <span class="comp-stat-label">Products</span>
                    </div>
                    <div class="comp-stat">
                        <span class="comp-stat-value">${lastCrawl}</span>
                        <span class="comp-stat-label">Last Crawl</span>
                    </div>
                </div>
                <div class="comp-card-footer">
                    ${schedBadge}
                    <button class="comp-view-btn">View Products <i class="fa-solid fa-arrow-right"></i></button>
                </div>
            `;

            // Events
            card.querySelector('.comp-view-btn').addEventListener('click', () => openDetail(comp));
            card.querySelector('.comp-delete-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                deleteCompetitor(comp.id);
            });

            cardsGrid.appendChild(card);
        });
    }

    async function openDetail(comp) {
        biLoading.classList.remove('hidden');
        loadingText.textContent = 'Loading product data...';

        try {
            const data = await apiFetch(`/api/bi/products/${comp.id}`);
            biLoading.classList.add('hidden');
            showCompetitorDetail(comp, data.products || [], data.changes);
        } catch (err) {
            biLoading.classList.add('hidden');
            alert('Failed to load products: ' + err.message);
        }
    }

    function showCompetitorDetail(comp, products, changes) {
        currentCompetitorId = comp.id;
        currentProducts = products;

        cardsGrid.classList.add('hidden');
        biEmpty.classList.add('hidden');
        detailPanel.classList.remove('hidden');

        detailName.textContent = comp.name || 'Competitor';
        if (comp.favicon_url) {
            detailFavicon.src = comp.favicon_url;
            detailFavicon.style.display = 'inline';
        } else {
            detailFavicon.style.display = 'none';
        }

        // Hide AI bar
        aiBar.classList.add('hidden');
        aiAnswerBox.classList.add('hidden');

        renderProductsTable(products, changes);

        // Crawl meta
        crawlMeta.innerHTML = `
            <span><i class="fa-solid fa-box"></i> ${products.length} products</span>
            <span><i class="fa-solid fa-link"></i> <a href="${comp.url}" target="_blank">${truncateUrl(comp.url)}</a></span>
        `;
    }

    function renderProductsTable(products, changes) {
        productsTbody.innerHTML = '';

        if (!products || products.length === 0) {
            productsEmpty.classList.remove('hidden');
            document.getElementById('products-table').classList.add('hidden');
            return;
        }

        productsEmpty.classList.add('hidden');
        document.getElementById('products-table').classList.remove('hidden');

        // Build change lookup
        const priceDrops = {};
        const priceIncs = {};
        const newProds = {};
        const restocked = {};
        const oos = {};

        if (changes) {
            (changes.price_drops || []).forEach(p => priceDrops[p.name.toLowerCase()] = p);
            (changes.price_increases || []).forEach(p => priceIncs[p.name.toLowerCase()] = p);
            (changes.new_products || []).forEach(p => newProds[p.name.toLowerCase()] = true);
            (changes.restocked || []).forEach(p => restocked[p.name.toLowerCase()] = true);
            (changes.out_of_stock || []).forEach(p => oos[p.name.toLowerCase()] = true);
        }

        products.forEach(p => {
            const key = p.name.toLowerCase().trim();
            const tr = document.createElement('tr');

            // Price cell
            let priceHtml = '—';
            if (p.price != null) {
                const sym = currSymbol(p.currency);
                priceHtml = `${sym}${formatNum(p.price)}`;
                if (p.original_price && p.original_price > p.price) {
                    priceHtml += ` <span class="original-price">${sym}${formatNum(p.original_price)}</span>`;
                }
            }

            // Change indicator
            let changeIndicator = '';
            if (priceDrops[key]) {
                const d = priceDrops[key];
                changeIndicator = `<span class="change-badge drop">▼ ${d.change_pct}%</span>`;
            } else if (priceIncs[key]) {
                const d = priceIncs[key];
                changeIndicator = `<span class="change-badge increase">▲ ${d.change_pct}%</span>`;
            } else if (newProds[key]) {
                changeIndicator = `<span class="change-badge new-badge">NEW</span>`;
            }

            // Stock pill
            let stockHtml = '<span class="stock-pill unknown">—</span>';
            if (p.in_stock === true) {
                stockHtml = '<span class="stock-pill in-stock">In Stock</span>';
                if (restocked[key]) stockHtml = '<span class="stock-pill restocked">Restocked!</span>';
            } else if (p.in_stock === false) {
                stockHtml = '<span class="stock-pill out-of-stock">Out of Stock</span>';
            }

            // Discount
            let discountHtml = '—';
            if (p.discount) {
                discountHtml = `<span class="discount-badge">${escapeHtml(p.discount)}</span>`;
            }

            tr.innerHTML = `
                <td class="td-name">${escapeHtml(p.name)} ${changeIndicator}</td>
                <td class="td-price">${priceHtml}</td>
                <td class="td-discount">${discountHtml}</td>
                <td class="td-stock">${stockHtml}</td>
                <td class="td-category">${escapeHtml(p.category || '—')}</td>
            `;
            productsTbody.appendChild(tr);
        });
    }

    // --- Sorting ---
    document.querySelectorAll('.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const field = th.dataset.sort;
            if (sortField === field) {
                sortAsc = !sortAsc;
            } else {
                sortField = field;
                sortAsc = true;
            }
            const sorted = [...currentProducts].sort((a, b) => {
                let va = a[field], vb = b[field];
                if (va == null) va = '';
                if (vb == null) vb = '';
                if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
                return sortAsc ? va - vb : vb - va;
            });
            renderProductsTable(sorted, null);
        });
    });

    // --- Back Button ---
    if (backBtn) {
        backBtn.addEventListener('click', () => {
            detailPanel.classList.add('hidden');
            window.loadCompetitors();
        });
    }

    // --- Re-crawl ---
    if (recrawlBtn) {
        recrawlBtn.addEventListener('click', async () => {
            if (!currentCompetitorId) return;
            recrawlBtn.disabled = true;
            recrawlBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Crawling...';

            try {
                const data = await apiFetch(`/api/bi/crawl/${currentCompetitorId}`, { method: 'POST' });
                if (data.error) {
                    alert('Re-crawl error: ' + data.error);
                } else {
                    currentProducts = data.products || [];
                    renderProductsTable(currentProducts, data.changes);
                    crawlMeta.innerHTML = `
                        <span><i class="fa-solid fa-box"></i> ${currentProducts.length} products</span>
                        <span><i class="fa-solid fa-bolt"></i> ${data.duration_ms}ms</span>
                    `;
                    if (data.changes && data.changes.total_changes > 0) {
                        crawlMeta.innerHTML += `<span class="changes-detected"><i class="fa-solid fa-triangle-exclamation"></i> ${data.changes.total_changes} changes detected!</span>`;
                    }
                }
            } catch (err) {
                alert('Re-crawl failed: ' + err.message);
            } finally {
                recrawlBtn.disabled = false;
                recrawlBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Re-crawl';
            }
        });
    }

    // --- Schedule Modal ---
    if (scheduleBtn) {
        scheduleBtn.addEventListener('click', () => {
            scheduleModal.classList.remove('hidden');
        });
    }
    if (closeScheduleModal) {
        closeScheduleModal.addEventListener('click', () => scheduleModal.classList.add('hidden'));
    }
    if (scheduleModal) {
        scheduleModal.addEventListener('click', (e) => {
            if (e.target === scheduleModal) scheduleModal.classList.add('hidden');
        });
    }
    freqOptions.forEach(opt => {
        opt.addEventListener('click', () => {
            freqOptions.forEach(o => o.classList.remove('active'));
            opt.classList.add('active');
        });
    });
    if (saveScheduleBtn) {
        saveScheduleBtn.addEventListener('click', async () => {
            const freq = document.querySelector('.freq-option.active')?.dataset.freq || 'daily';
            try {
                await apiFetch('/api/bi/schedule', {
                    method: 'POST',
                    body: { competitor_id: currentCompetitorId, frequency: freq }
                });
                scheduleModal.classList.add('hidden');
                scheduleBtn.innerHTML = `<i class="fa-solid fa-check"></i> ${freq}`;
                scheduleBtn.classList.add('scheduled');
            } catch (err) {
                alert('Failed to save schedule: ' + err.message);
            }
        });
    }

    // --- AI Q&A ---
    if (askAiToggle) {
        askAiToggle.addEventListener('click', () => {
            aiBar.classList.toggle('hidden');
            if (!aiBar.classList.contains('hidden')) {
                aiInput.focus();
            }
        });
    }
    if (aiSubmit) {
        aiSubmit.addEventListener('click', () => askAI());
    }
    if (aiInput) {
        aiInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') askAI();
        });
    }

    async function askAI() {
        const q = aiInput.value.trim();
        if (!q) return;

        aiAnswerBox.classList.remove('hidden');
        aiAnswerBox.innerHTML = `
            <div class="ai-spinner-container">
                <i class="fa-solid fa-asterisk ai-spinner-logo"></i>
                <div class="ai-spinner-text">Analyzing competitor data...</div>
            </div>
        `;
        aiSubmit.disabled = true;

        try {
            const data = await apiFetch('/api/bi/analyze', {
                method: 'POST',
                body: { competitor_id: currentCompetitorId, question: q }
            });

            if (data.error) {
                aiAnswerBox.innerHTML = `<div class="ai-error">${escapeHtml(data.error)}</div>`;
            } else {
                aiAnswerBox.innerHTML = `<div class="ai-response">${marked.parse(data.answer)}</div>`;
            }
        } catch (err) {
            aiAnswerBox.innerHTML = `<div class="ai-error">Failed: ${err.message}</div>`;
        } finally {
            aiSubmit.disabled = false;
        }
    }

    // --- Delete Competitor ---
    async function deleteCompetitor(id) {
        if (!confirm('Remove this competitor and all its data?')) return;
        try {
            await apiFetch(`/api/bi/competitors/${id}`, { method: 'DELETE' });
            window.loadCompetitors();
        } catch (err) {
            alert('Failed to delete: ' + err.message);
        }
    }

    // --- Utilities ---
    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function truncateUrl(url) {
        try {
            const u = new URL(url);
            return u.hostname.replace(/^www\./, '');
        } catch { return url ? url.substring(0, 40) : ''; }
    }
    function currSymbol(c) {
        const map = { USD: '$', INR: '₹', EUR: '€', GBP: '£' };
        return map[c] || (c || '$');
    }
    function formatNum(n) {
        if (n == null) return '—';
        return Number(n).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    }
    function timeAgo(dateStr) {
        try {
            const d = new Date(dateStr + (dateStr.includes('Z') ? '' : 'Z'));
            const s = Math.floor((Date.now() - d.getTime()) / 1000);
            if (s < 60) return 'just now';
            if (s < 3600) return `${Math.floor(s / 60)}m ago`;
            if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
            return `${Math.floor(s / 86400)}d ago`;
        } catch { return dateStr || '—'; }
    }

})();
