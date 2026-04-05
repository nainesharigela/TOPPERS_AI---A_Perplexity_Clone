// --- API Configuration (Initialize immediately for other scripts) ---
// Use the current origin if on a web server, otherwise fallback to localhost:5001
const API_BASE = (window.location.protocol !== 'file:') 
    ? (window.location.origin || '') 
    : 'http://127.0.0.1:5001';
window.API_BASE = API_BASE;
console.log('📡 API Base initialized at top level:', API_BASE);

document.addEventListener('DOMContentLoaded', () => {

    // --- Theme Management ---
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    const savedTheme = localStorage.getItem('topper_theme') || 'dark';

    function applyTheme(theme) {
        if (theme === 'light') {
            document.documentElement.setAttribute('data-theme', 'light');
            if (themeToggleBtn) themeToggleBtn.innerHTML = '<i class="fa-solid fa-moon"></i>';
        } else {
            document.documentElement.removeAttribute('data-theme');
            if (themeToggleBtn) themeToggleBtn.innerHTML = '<i class="fa-solid fa-sun"></i>';
        }
        localStorage.setItem('topper_theme', theme);
    }
    applyTheme(savedTheme);

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
            applyTheme(current === 'light' ? 'dark' : 'light');
        });
    }

    // --- Space Background Generation ---
    function generateStars(count) {
        let stars = '';
        for (let i = 0; i < count; i++) {
            const x = Math.floor(Math.random() * window.innerWidth);
            const y = Math.floor(Math.random() * 2000); // 2000px height loop
            // some stars twinkle implicitly but we keep them purely static for perf, size varies by shadow offset
            stars += `${x}px ${y}px #FFF${i < count - 1 ? ', ' : ''}`;
        }
        return stars;
    }

    const starsSmall = document.getElementById('stars-small');
    const starsMedium = document.getElementById('stars-medium');
    const starsLarge = document.getElementById('stars-large');

    function renderStars() {
        if (starsSmall) starsSmall.style.boxShadow = generateStars(350);
        if (starsMedium) {
            starsMedium.style.width = '2px'; starsMedium.style.height = '2px';
            starsMedium.style.boxShadow = generateStars(100);
        }
        if (starsLarge) {
            starsLarge.style.width = '3px'; starsLarge.style.height = '3px';
            starsLarge.style.boxShadow = generateStars(40);
        }
    }
    renderStars();
    
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(renderStars, 300);
    });

    // --- Shooting Stars ---
    const shootingStarsContainer = document.getElementById('shooting-stars-container');
    function triggerShootingStar() {
        if (!shootingStarsContainer) return;
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        if (document.documentElement.getAttribute('data-theme') === 'light') return;

        const star = document.createElement('div');
        star.className = 'shooting-star';
        
        const startX = Math.random() < 0.5 ? -100 : Math.random() * (window.innerWidth / 2);
        const startY = startX === -100 ? Math.random() * (window.innerHeight / 2) : -100;
        
        star.style.left = `${startX}px`;
        star.style.top = `${startY}px`;
        
        const angle = 20 + Math.random() * 40; 
        star.style.transform = `rotate(${angle}deg)`;
        
        shootingStarsContainer.appendChild(star);
        setTimeout(() => star.remove(), 2000);
    }

    setInterval(() => {
        if (Math.random() > 0.4) triggerShootingStar();
    }, 4000);


    // --- Cursor Particles ---
    const canvas = document.getElementById('cursor-particles');
    const ctx = canvas.getContext('2d');
    let particles = [];
    const maxParticles = 150;

    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    class Particle {
        constructor(x, y, isClick = false) {
            this.x = x;
            this.y = y;
            this.isClick = isClick;
            const theme = document.documentElement.getAttribute('data-theme') || 'dark';
            
            // Randomize velocity
            const speedScale = isClick ? 5 : 2;
            this.vx = (Math.random() - 0.5) * speedScale;
            this.vy = (Math.random() - 0.5) * speedScale;
            
            // Randomize size and life
            this.size = Math.random() * 3 + 1;
            this.maxLife = Math.random() * 1000 + 500; // 0.5s to 1.5s
            this.life = this.maxLife;
            
            // Theme-aware colors
            if (theme === 'light') {
                const colors = ['rgba(255,255,255,0.8)', '#87ceeb', '#ffd700'];
                this.color = colors[Math.floor(Math.random() * colors.length)];
                this.type = 'circle';
            } else {
                const colors = ['#ffffff', '#add8e6', '#fffacd'];
                this.color = colors[Math.floor(Math.random() * colors.length)];
                this.type = Math.random() > 0.5 ? 'star' : 'circle';
            }
        }

        draw() {
            const opacity = this.life / this.maxLife;
            ctx.globalAlpha = opacity;
            ctx.fillStyle = this.color;
            ctx.beginPath();
            
            if (this.type === 'star') {
                this.drawStar(this.x, this.y, 4, this.size, this.size/2);
            } else {
                ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            }
            ctx.fill();
        }

        drawStar(cx, cy, spikes, outerRadius, innerRadius) {
            let rot = Math.PI / 2 * 3;
            let x = cx;
            let y = cy;
            let step = Math.PI / spikes;

            ctx.moveTo(cx, cy - outerRadius);
            for (let i = 0; i < spikes; i++) {
                x = cx + Math.cos(rot) * outerRadius;
                y = cy + Math.sin(rot) * outerRadius;
                ctx.lineTo(x, y);
                rot += step;

                x = cx + Math.cos(rot) * innerRadius;
                y = cy + Math.sin(rot) * innerRadius;
                ctx.lineTo(x, y);
                rot += step;
            }
            ctx.lineTo(cx, cy - outerRadius);
            ctx.closePath();
        }

        update(deltaTime) {
            this.x += this.vx;
            this.y += this.vy;
            this.life -= deltaTime;
            this.size *= 0.98; // Shrink
        }
    }

    let lastTime = 0;
    function animateParticles(timestamp) {
        const deltaTime = timestamp - lastTime;
        lastTime = timestamp;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Limit particles for performance
        if (particles.length > maxParticles) {
            particles = particles.slice(-maxParticles);
        }

        for (let i = particles.length - 1; i >= 0; i--) {
            particles[i].update(deltaTime);
            particles[i].draw();
            if (particles[i].life <= 0 || particles[i].size <= 0.1) {
                particles.splice(i, 1);
            }
        }

        if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            requestAnimationFrame(animateParticles);
        }
    }
    requestAnimationFrame(animateParticles);

    window.addEventListener('mousemove', (e) => {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        particles.push(new Particle(e.clientX, e.clientY));
    });

    window.addEventListener('click', (e) => {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        const burstCount = 20 + Math.floor(Math.random() * 10);
        for (let i = 0; i < burstCount; i++) {
            particles.push(new Particle(e.clientX, e.clientY, true));
        }
    });

    // --- State Management ---
    let chats = JSON.parse(localStorage.getItem('topper_chats') || '[]');
    let activeChatId = null;

    // --- DOM Elements ---
    const searchInput = document.getElementById('search-input');
    const chatHistory = document.getElementById('chat-history-container');
    const greeting = document.querySelector('.greeting');
    const landingView = document.getElementById('landing-view');
    const mainArea = document.getElementById('main-area');
    const tryComputerSection = document.querySelector('.try-computer-section');
    const recentChatsList = document.getElementById('recent-chats-list');
    const noHistoryMsg = document.getElementById('no-history-msg');
    const clearHistoryBtn = document.getElementById('clear-history-btn');
    const newThreadBtn = document.getElementById('new-thread-btn');

    // Auth Elements
    const authOverlay = document.getElementById('auth-overlay');
    const signInTrigger = document.getElementById('sign-in-trigger');
    const closeAuthBtn = document.getElementById('close-auth');
    const authEmail = document.getElementById('auth-email');
    const emailSubmit = document.getElementById('email-submit');
    
    // checkServerHealth();
    
    // --- RAG Elements ---
    const uploadBtn = document.getElementById('upload-btn');
    const pdfUploadInput = document.getElementById('pdf-upload');
    const docStatus = document.getElementById('doc-status');
    const docName = docStatus.querySelector('.doc-name');
    const removeFileBtn = document.getElementById('remove-file-btn');
    const pdfModal = document.getElementById('pdf-modal');
    const pdfFrame = document.getElementById('pdf-frame');
    const pdfTitle = document.getElementById('pdf-title');
    const closePdfBtn = document.getElementById('close-pdf');

    let currentPdfUrl = null;

    // --- Web Search Elements ---
    const webSearchToggle = document.getElementById('web-search-toggle');
    let isWebSearchEnabled = true; // Auto-enabled by default for discovery
    if (webSearchToggle) webSearchToggle.classList.add('search-active');

    // --- initialization ---
    renderHistorySidebar();

    // --- View Switching Logic ---
    const competitorsView = document.getElementById('competitors-view');
    const reportsView = document.getElementById('reports-view');
    const trendsView = document.getElementById('trends-view');
    const searchContainer = document.querySelector('.search-container');
    const allNavItems = document.querySelectorAll('.nav-item[data-view]');
    let currentView = 'search';

    function switchView(viewName) {
        currentView = viewName;

        // Update nav active state
        allNavItems.forEach(item => {
            if (item.dataset.view === viewName) item.classList.add('active');
            else item.classList.remove('active');
        });

        // Hide all views
        if (landingView) landingView.style.display = 'none';
        if (searchContainer) searchContainer.style.display = 'none';
        chatHistory.classList.add('hidden');
        if (competitorsView) competitorsView.classList.add('hidden');
        if (reportsView) reportsView.classList.add('hidden');
        if (trendsView) trendsView.classList.add('hidden');
        if (mainArea) mainArea.classList.remove('chatting');

        switch (viewName) {
            case 'search':
                if (activeChatId) {
                    chatHistory.classList.remove('hidden');
                    if (mainArea) mainArea.classList.add('chatting');
                } else {
                    if (landingView) landingView.style.display = 'flex';
                }
                if (searchContainer) searchContainer.style.display = 'flex';
                break;
            case 'competitors':
                if (competitorsView) {
                    competitorsView.classList.remove('hidden');
                    if (mainArea) mainArea.classList.add('chatting');
                    if (window.loadCompetitors) window.loadCompetitors();
                }
                break;
            case 'reports':
                if (reportsView) {
                    reportsView.classList.remove('hidden');
                    if (mainArea) mainArea.classList.add('chatting');
                    if (window.loadReports) window.loadReports();
                }
                break;
            case 'trends':
                if (trendsView) {
                    trendsView.classList.remove('hidden');
                    if (mainArea) mainArea.classList.add('chatting');
                    // We don't auto-load anything yet, wait for user input
                }
                break;
        }
    }

    allNavItems.forEach(item => {
        item.addEventListener('click', () => {
            switchView(item.dataset.view);
        });
    });

    // --- Chat Logic ---

    function saveChats() {
        localStorage.setItem('topper_chats', JSON.stringify(chats));
        renderHistorySidebar();
    }

    function startNewChat() {
        activeChatId = null;
        chatHistory.innerHTML = '';
        chatHistory.classList.add('hidden');
        if(greeting) greeting.style.display = 'block';
        if(landingView) landingView.style.display = 'flex';
        if(mainArea) mainArea.classList.remove('chatting');
        if(tryComputerSection) tryComputerSection.style.display = 'flex';
        searchInput.value = '';
        searchInput.focus();
        clearFile(); // Also clear any leftover file context
        clearFile(); // Also clear any leftover file context
    }

    function loadChat(id) {
        const chat = chats.find(c => c.id === id);
        if (!chat) return;

        activeChatId = id;
        chatHistory.innerHTML = '';
        chatHistory.classList.remove('hidden');
        if(greeting) greeting.style.display = 'none';
        if(landingView) landingView.style.display = 'none';
        if(mainArea) mainArea.classList.add('chatting');
        if(tryComputerSection) tryComputerSection.style.display = 'none';

        chat.messages.forEach(msg => {
            const msgDiv = appendMessageToUI(msg.text, msg.role === 'user');
            if (msg.role === 'ai' && msg.sources && msg.sources.length > 0) {
                let ftr = msgDiv.querySelector('.msg-footer');
                if (ftr) {
                    let btn = document.createElement('button');
                    btn.className = 'sources-pill-btn';
                    btn.innerHTML = `<i class="fa-solid fa-layer-group"></i> ${msg.sources.length} sources`;
                    btn.onclick = () => openSourcesSidebar(msg.sources);
                    ftr.appendChild(btn);
                    msgDiv.dataset.sources = JSON.stringify(msg.sources);
                    
                    // Re-render inline citations for loaded message
                    let html = marked.parse(msg.text);
                    html = html.replace(/\[(\d+)\]/g, (match, p1) => {
                        let sourceDomain = p1;
                        try {
                            let idx = parseInt(p1) - 1;
                            if (msg.sources[idx]) {
                                sourceDomain = new URL(msg.sources[idx].url).hostname.replace(/^www\./, '').split('.')[0];
                            }
                        } catch(e){}
                        return `<span class="inline-source" data-source="${p1}">${sourceDomain}</span>`;
                    });
                    msgDiv.querySelector('.msg-bubble').innerHTML = html;
                }
            }
        });
        
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    function deleteChat(id, e) {
        if (e) e.stopPropagation();
        chats = chats.filter(c => c.id !== id);
        if (activeChatId === id) startNewChat();
        saveChats();
    }

    function clearAllHistory() {
        if (confirm('Are you sure you want to clear all chat history?')) {
            chats = [];
            startNewChat();
            saveChats();
        }
    }

    function appendMessageToUI(text, isUser) {
        chatHistory.classList.remove('hidden');
        if(greeting) greeting.style.display = 'none';
        if(landingView) landingView.style.display = 'none';
        if(mainArea) mainArea.classList.add('chatting');
        if(tryComputerSection) tryComputerSection.style.display = 'none';

        const msgDiv = document.createElement('div');
        msgDiv.className = `chat-message ${isUser ? 'user' : 'ai'}`;
        
        const labelText = isUser ? 'You' : "TOPPERS AI";
        
        msgDiv.innerHTML = `
            <div class="msg-label">${labelText}</div>
            <div class="msg-bubble"></div>
            <div class="msg-footer"></div>
        `;
        msgDiv.querySelector('.msg-bubble').textContent = text;
        
        chatHistory.appendChild(msgDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;

        // Requirement: Hide the file badge after the first message is sent with it
        if (isUser && !docStatus.classList.contains('hidden')) {
            docStatus.classList.add('hidden');
            console.log('📂 File badge hidden after first message. Memory persists on backend.');
        }

        return msgDiv;
    }

    function renderHistorySidebar() {
        recentChatsList.innerHTML = '';
        
        if (chats.length === 0) {
            noHistoryMsg.classList.remove('hidden');
            clearHistoryBtn.classList.add('hidden');
            return;
        }

        noHistoryMsg.classList.add('hidden');
        clearHistoryBtn.classList.remove('hidden');

        // Sort by timestamp desc
        const sortedChats = [...chats].sort((a, b) => b.timestamp - a.timestamp);

        sortedChats.forEach(chat => {
            const item = document.createElement('div');
            item.className = `chat-history-item ${activeChatId === chat.id ? 'active' : ''}`;
            item.innerHTML = `
                <span>${chat.title || 'New Chat'}</span>
                <i class="fa-solid fa-trash-can delete-chat-btn" title="Delete chat"></i>
            `;
            
            item.addEventListener('click', () => loadChat(chat.id));
            item.querySelector('.delete-chat-btn').addEventListener('click', (e) => deleteChat(chat.id, e));
            
            recentChatsList.appendChild(item);
        });
    }

    async function handleChatSubmission(prompt) {
        if (!prompt) return;

        // If it's a new chat, create the record
        if (!activeChatId) {
            activeChatId = Date.now().toString();
            chats.push({
                id: activeChatId,
                title: prompt.substring(0, 30) + (prompt.length > 30 ? '...' : ''),
                messages: [],
                timestamp: Date.now()
            });
        }

        const currentChat = chats.find(c => c.id === activeChatId);
        currentChat.messages.push({ role: 'user', text: prompt });
        currentChat.timestamp = Date.now();
        
        // --- Conversation Memory: Take last 6 messages (3 turns) ---
        const historyLimit = 6;
        const msgHistory = currentChat.messages.slice(0, -1); // Exclude current prompt
        const trimmedHistory = msgHistory.slice(-historyLimit).map(m => ({
            role: m.role === 'user' ? 'user' : 'model',
            parts: m.text
        }));

        appendMessageToUI(prompt, true);
        const aiMsgDiv = appendMessageToUI('', false);
        const aiBubble = aiMsgDiv.querySelector('.msg-bubble');
        
        // Unified UI Spinner
        aiBubble.innerHTML = `
            <div class="ai-spinner-container">
                <i class="fa-solid fa-asterisk ai-spinner-logo"></i>
                <div class="ai-spinner-text">${isWebSearchEnabled ? 'Searching the web...' : 'Thinking...'}</div>
            </div>
        `;
        let isFirstChunk = true;

        try {
            const response = await fetch(`${API_BASE}/api/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    prompt: prompt,
                    history: trimmedHistory,
                    webSearch: isWebSearchEnabled
                })
            });

            if (!response.ok) {
                if (response.status === 429) {
                    const result = await response.json();
                    throw new Error(result.error);
                }
                throw new Error(`Server responded with ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let fullAiResponse = '';
            
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const parts = buffer.split('\n\n');
                buffer = parts.pop();

                for (const part of parts) {
                    if (part.startsWith('data: ')) {
                        try {
                            const dataString = part.replace(/^data: /, '').trim();
                            if (!dataString) continue;
                            const parsed = JSON.parse(dataString);
                            
                            if (isFirstChunk) {
                                aiBubble.textContent = '';
                                isFirstChunk = false;
                            }

                            if (parsed.sources && parsed.sources.length > 0) {
                                let ftr = aiMsgDiv.querySelector('.msg-footer');
                                if (ftr && !ftr.hasChildNodes()) {
                                    let btn = document.createElement('button');
                                    btn.className = 'sources-pill-btn';
                                    btn.innerHTML = `<i class="fa-solid fa-layer-group"></i> ${parsed.sources.length} sources`;
                                    btn.onclick = () => openSourcesSidebar(parsed.sources);
                                    ftr.appendChild(btn);
                                }
                                aiMsgDiv.dataset.sources = JSON.stringify(parsed.sources);
                            } else if (parsed.text) {
                                fullAiResponse += parsed.text;
                                let html = marked.parse(fullAiResponse);
                                html = html.replace(/\[(\d+)\]/g, (match, p1) => {
                                    let sourceDomain = p1;
                                    try {
                                        if (aiMsgDiv.dataset.sources) {
                                            let sources = JSON.parse(aiMsgDiv.dataset.sources);
                                            let idx = parseInt(p1) - 1;
                                            if (sources[idx]) {
                                                sourceDomain = new URL(sources[idx].url).hostname.replace(/^www\./, '').split('.')[0];
                                            }
                                        }
                                    } catch(e){}
                                    return `<span class="inline-source" data-source="${p1}">${sourceDomain}</span>`;
                                });
                                aiBubble.innerHTML = html;
                            } else if (parsed.error) {
                                fullAiResponse += `\n[Error: ${parsed.error}]`;
                                aiBubble.innerHTML = marked.parse(fullAiResponse);
                            }
                            chatHistory.scrollTop = chatHistory.scrollHeight;
                        } catch (e) {}
                    }
                }
            }
            
            // Save full AI response to the message history
            const sourcesToSave = aiMsgDiv.dataset.sources ? JSON.parse(aiMsgDiv.dataset.sources) : null;
            currentChat.messages.push({ role: 'ai', text: fullAiResponse, sources: sourcesToSave });
            saveChats();

        } catch (err) {
            aiBubble.textContent = 'Connection Error. (' + err.message + ')';
        } finally {
            searchInput.disabled = false;
            searchInput.focus();
        }
    }

    // --- Sources Sidebar Logic ---
    const sourcesSidebar = document.getElementById('sources-sidebar');
    const sourcesListContainer = document.getElementById('sources-list-container');
    const sourcesSidebarTitle = document.getElementById('sources-sidebar-title');
    const closeSourcesBtn = document.getElementById('close-sources-btn');

    function openSourcesSidebar(sources) {
        if (!sources || sources.length === 0) return;
        sourcesSidebarTitle.textContent = `${sources.length} sources`;
        sourcesListContainer.innerHTML = '';

        sources.forEach((s) => {
            let cleanUrl = s.url;
            try { cleanUrl = new URL(s.url).hostname.replace(/^www\./, ''); } catch(e){}
            let faviconUrl = `https://www.google.com/s2/favicons?domain=${cleanUrl}&sz=32`;

            const card = document.createElement('a');
            card.className = 'source-card-vertical';
            card.href = s.url;
            card.target = '_blank';
            card.innerHTML = `
                <div class="source-info">
                    <div class="source-domain">
                        <img src="${faviconUrl}" alt="" onerror="this.style.display='none'">
                        ${cleanUrl}
                    </div>
                    <div class="source-title">${s.title}</div>
                </div>
            `;
            sourcesListContainer.appendChild(card);
        });

        sourcesSidebar.classList.add('open');
    }

    if (closeSourcesBtn) {
        closeSourcesBtn.addEventListener('click', () => {
            sourcesSidebar.classList.remove('open');
        });
    }

    // Delegate click for inline sources
    chatHistory.addEventListener('click', (e) => {
        if (e.target.classList.contains('inline-source')) {
            const msgDiv = e.target.closest('.chat-message');
            if (msgDiv && msgDiv.dataset.sources) {
                try {
                    const sources = JSON.parse(msgDiv.dataset.sources);
                    openSourcesSidebar(sources);
                } catch(err) {}
            }
        }
    });

    // --- Listeners ---

    searchInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            const prompt = searchInput.value.trim();
            if (!prompt) return;

            searchInput.value = '';
            searchInput.style.height = 'auto';
            searchInput.disabled = true;
            handleChatSubmission(prompt);
        }
    });

    newThreadBtn.addEventListener('click', startNewChat);
    clearHistoryBtn.addEventListener('click', clearAllHistory);

    // Auth Modal Listeners
    if (signInTrigger) {
        signInTrigger.addEventListener('click', () => {
            authOverlay.classList.add('active');
        });
    }

    if (closeAuthBtn) {
        closeAuthBtn.addEventListener('click', () => {
            authOverlay.classList.remove('active');
        });
    }

    // Close auth on background click
    authOverlay.addEventListener('click', (e) => {
        if (e.target === authOverlay) authOverlay.classList.remove('active');
    });

    // Email Validation toggle
    if (authEmail && emailSubmit) {
        authEmail.addEventListener('input', () => {
            const email = authEmail.value.trim();
            const isValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
            if (isValid) emailSubmit.classList.add('active');
            else emailSubmit.classList.remove('active');
        });
    }

    // --- RAG Upload Logic ---

    uploadBtn.addEventListener('click', () => pdfUploadInput.click());

    pdfUploadInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        // Show loading status
        docName.textContent = 'Indexing...';
        docStatus.classList.remove('hidden');
        uploadBtn.disabled = true;
        uploadBtn.style.opacity = '0.5';

        const formData = new FormData();
        formData.append('file', file);

        try {
            console.log(`Starting upload to ${API_BASE}/api/upload...`);
            const response = await fetch(`${API_BASE}/api/upload`, {
                method: 'POST',
                body: formData
            });

            console.log('Upload response status:', response.status);
            
            // Validate that we got a JSON response
            const contentType = response.headers.get("content-type");
            if (!contentType || !contentType.includes("application/json")) {
                const text = await response.text();
                console.error("Server returned non-JSON response:", text);
                throw new Error("Server returned an invalid response (HTML instead of JSON). Make sure app.py is running correctly.");
            }

            const result = await response.json();
            
            if (response.ok) {
                // Create a local blob URL for previewing
                if (currentPdfUrl) URL.revokeObjectURL(currentPdfUrl);
                currentPdfUrl = URL.createObjectURL(file);
                
                docName.textContent = `📄 ${file.name.substring(0, 15)}...`;
                docStatus.classList.remove('hidden');
                docStatus.classList.add('active');
            } else {
                alert('Error indexing PDF: ' + result.error);
                docStatus.classList.add('hidden');
            }
        } catch (err) {
            console.error("Upload fetch failed:", err);
            alert(`Upload failed: ${err.message}. (Target: ${API_BASE}/api/upload). Make sure app.py is running!`);
            docStatus.classList.add('hidden');
        } finally {            uploadBtn.disabled = false;
            uploadBtn.style.opacity = '1';
            pdfUploadInput.value = ''; // Reset for next upload
        }
    });

    async function clearFile() {
        try {
            await fetch(`${API_BASE}/api/clear`, { method: 'POST' });
            docStatus.classList.add('hidden');
            docStatus.classList.remove('active');
            if (currentPdfUrl) URL.revokeObjectURL(currentPdfUrl);
            currentPdfUrl = null;
            console.log('📂 Context cleared.');
        } catch (err) {
            console.error('Failed to clear file:', err);
        }
    }

    removeFileBtn.addEventListener('click', (e) => {
        e.stopPropagation(); // Don't trigger the viewer
        clearFile();
    });

    // --- PDF Viewer Handlers ---

    docStatus.addEventListener('click', (e) => {
        if (e.target.closest('#remove-file-btn')) return;
        if (!currentPdfUrl) return;
        pdfFrame.src = currentPdfUrl;
        pdfModal.classList.remove('hidden');
    });

    closePdfBtn.addEventListener('click', () => {
        pdfModal.classList.add('hidden');
        pdfFrame.src = '';
    });

    // Close on overlay click
    pdfModal.addEventListener('click', (e) => {
        if (e.target === pdfModal) {
            pdfModal.classList.add('hidden');
            pdfFrame.src = '';
        }
    });

    // --- Web Search Toggle Logic ---
    webSearchToggle.addEventListener('click', (e) => {
        e.preventDefault();
        isWebSearchEnabled = !isWebSearchEnabled;
        if (isWebSearchEnabled) {
            webSearchToggle.classList.add('search-active');
        } else {
            webSearchToggle.classList.remove('search-active');
        }
    });

});
