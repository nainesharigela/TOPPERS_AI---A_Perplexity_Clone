/**
 * Market Trends Intelligence UI — trends.js
 * Handles the Market Trends UI, analyzing topics, and AI chat.
 */
(function() {
    // Dynamically get API base to avoid initialization race conditions
    const getAPI = () => window.API_BASE || 'http://127.0.0.1:5001';

    const trendsView = document.getElementById('trends-view');
    const topicInput = document.getElementById('trend-topic-input');
    const analyzeBtn = document.getElementById('analyze-trend-btn');
    const loadingUI = document.getElementById('trend-loading');
    const emptyUI = document.getElementById('trend-empty');
    const resultsPanel = document.getElementById('trend-results');
    
    // UI Elements
    const sentimentRing = document.getElementById('sentiment-ring');
    const sentimentValue = document.getElementById('sentiment-value');
    const sentimentLabel = document.getElementById('sentiment-label');
    const keywordsList = document.getElementById('trend-keywords-list');
    const mentionsList = document.getElementById('trend-mentions-list');
    const summaryContent = document.getElementById('trend-summary-content');

    // Chat Elements
    const qaInput = document.getElementById('trend-qa-input');
    const qaSubmit = document.getElementById('trend-qa-submit');
    const qaAnswer = document.getElementById('trend-qa-answer');

    let currentReportId = null;

    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', analyzeTopic);
    }
    if (topicInput) {
        topicInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') analyzeTopic();
        });
    }

    async function analyzeTopic() {
        const topic = topicInput.value.trim();
        if (!topic) return;

        // UI State: Loading
        emptyUI.classList.add('hidden');
        resultsPanel.classList.add('hidden');
        loadingUI.classList.remove('hidden');
        analyzeBtn.disabled = true;

        try {
            const resp = await fetch(`${getAPI()}/api/bi/trends/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ topic })
            });

            const data = await resp.json();

            if (!resp.ok || data.error) {
                alert(`Trend Analysis Error: ${data.error}`);
                loadingUI.classList.add('hidden');
                emptyUI.classList.remove('hidden');
                return;
            }

            currentReportId = data.report_id;
            renderResults(data);

        } catch (err) {
            alert(`Failed to analyze trend: ${err.message}`);
            loadingUI.classList.add('hidden');
            emptyUI.classList.remove('hidden');
        } finally {
            analyzeBtn.disabled = false;
        }
    }

    function renderResults(data) {
        loadingUI.classList.add('hidden');
        resultsPanel.classList.remove('hidden');

        // 1. Sentiment Ring
        const score = data.sentiment_score || 50;
        const radius = 50;
        const circumference = 2 * Math.PI * radius;
        const offset = circumference - (score / 100) * circumference;
        
        sentimentRing.style.strokeDasharray = `${circumference} ${circumference}`;
        sentimentRing.style.strokeDashoffset = circumference; // Start empty
        
        // Trigger reflow
        sentimentRing.getBoundingClientRect();
        
        // Transition to score
        sentimentRing.style.strokeDashoffset = offset;
        sentimentValue.textContent = `${score}%`;

        if (score >= 70) {
            sentimentRing.style.stroke = '#4ade80'; // Green
            sentimentLabel.textContent = 'Positive';
            sentimentLabel.style.color = '#4ade80';
        } else if (score <= 40) {
            sentimentRing.style.stroke = '#f87171'; // Red
            sentimentLabel.textContent = 'Negative';
            sentimentLabel.style.color = '#f87171';
        } else {
            sentimentRing.style.stroke = '#fbbf24'; // Yellow
            sentimentLabel.textContent = 'Neutral';
            sentimentLabel.style.color = '#fbbf24';
        }

        // 2. Keywords
        const keys = data.keywords || [];
        keywordsList.innerHTML = '';
        if (keys.length === 0) {
            keywordsList.innerHTML = '<span class="empty-list">No significant keywords</span>';
        } else {
            keys.forEach(k => {
                const sp = document.createElement('span');
                sp.className = 'keyword-tag';
                sp.textContent = `#${k}`;
                keywordsList.appendChild(sp);
            });
        }

        // 3. Mentions
        const mentions = data.competitor_mentions || [];
        mentionsList.innerHTML = '';
        if (mentions.length === 0) {
            mentionsList.innerHTML = '<span class="empty-list">No dominant competitors detected</span>';
        } else {
            mentions.forEach(m => {
                const div = document.createElement('div');
                div.className = 'mention-item';
                div.innerHTML = `<strong>${escapeHtml(m.brand || 'Unknown')}</strong>: <span>${escapeHtml(m.insight || '')}</span>`;
                mentionsList.appendChild(div);
            });
        }

        // 4. Summary
        if (window.marked) {
            summaryContent.innerHTML = marked.parse(data.summary || 'No summary available.');
        } else {
            summaryContent.textContent = data.summary;
        }

        // Reset Q&A UI
        qaAnswer.classList.add('hidden');
        qaInput.value = '';
    }

    // Follow-up Q&A Logic
    if (qaSubmit) qaSubmit.addEventListener('click', askChat);
    if (qaInput) {
        qaInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') askChat();
        });
    }

    async function askChat() {
        const q = qaInput.value.trim();
        if (!q || !currentReportId) return;

        qaAnswer.classList.remove('hidden');
        qaAnswer.innerHTML = `
            <div class="ai-spinner-container">
                <i class="fa-solid fa-asterisk ai-spinner-logo"></i>
                <div class="ai-spinner-text">Digging into the data...</div>
            </div>
        `;
        qaSubmit.disabled = true;

        try {
            const resp = await fetch(`${getAPI()}/api/bi/trends/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: q, report_id: currentReportId })
            });

            const data = await resp.json();

            if (!resp.ok || data.error) {
                qaAnswer.innerHTML = `<div class="ai-error">${escapeHtml(data.error || 'Failed')}</div>`;
                return;
            }

            if (window.marked) {
                qaAnswer.innerHTML = `<div class="ai-response">${marked.parse(data.answer)}</div>`;
            } else {
                qaAnswer.innerHTML = `<div class="ai-response">${escapeHtml(data.answer)}</div>`;
            }

        } catch (err) {
            qaAnswer.innerHTML = `<div class="ai-error">Error: ${err.message}</div>`;
        } finally {
            qaSubmit.disabled = false;
        }
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
})();
