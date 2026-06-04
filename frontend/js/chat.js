/* ==========================================================================
   CHAT BOT INTERFACE — CHAT.JS
   ========================================================================== */

let chatInitialized = false;
let recognition = null;
let isRecording = false;

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function getSessionId() {
    let session = localStorage.getItem('rc_session_id');
    if (!session) {
        session = generateUUID();
        localStorage.setItem('rc_session_id', session);
    }
    return session;
}

// Format message timestamp
function formatTime(date = new Date()) {
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes}`;
}

// Auto scroll messages area to bottom
function scrollToBottom() {
    const chatMsg = document.getElementById('chat-messages');
    if (chatMsg) {
        chatMsg.scrollTop = chatMsg.scrollHeight;
    }
}

// Show/Hide typing animation
function showTypingIndicator(show = true) {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
        if (show) {
            indicator.style.display = 'flex';
            scrollToBottom();
        } else {
            indicator.style.display = 'none';
        }
    } else if (show) {
        // Create typing indicator dynamically if it doesn't exist
        const chatMsg = document.getElementById('chat-messages');
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.className = 'message-row bot';
        typingDiv.innerHTML = `
            <div class="avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="message-content-wrapper">
                <div class="message-bubble typing-box">
                    <div class="typing-dots"><span></span><span></span><span></span></div>
                </div>
            </div>
        `;
        chatMsg.appendChild(typingDiv);
        scrollToBottom();
    }
}

// Render OpenStreetMap (Leaflet) panels for detected Vinpearl locations.
// Returns descriptors to initialise after the element is attached to the DOM.
function buildLocationMaps(wrapperDiv, locations) {
    const mapEls = [];
    if (!Array.isArray(locations) || locations.length === 0) return mapEls;

    locations.forEach(loc => {
        const mapWrap = document.createElement('div');
        mapWrap.style.marginTop = '10px';

        const title = document.createElement('div');
        title.style.cssText = 'font-size:12px;color:#1e3a8a;font-weight:600;margin-bottom:4px;display:flex;align-items:center;gap:6px;';
        title.innerHTML = `<i class="fa-solid fa-location-dot"></i> ${loc.name}`;

        const mapEl = document.createElement('div');
        mapEl.style.cssText = 'height:220px;width:100%;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;position:relative;z-index:0;';

        mapWrap.appendChild(title);
        mapWrap.appendChild(mapEl);
        wrapperDiv.appendChild(mapWrap);
        mapEls.push({ el: mapEl, loc });
    });
    return mapEls;
}

function initLocationMaps(mapEls) {
    if (!mapEls.length || !window.L) return;
    mapEls.forEach(({ el, loc }) => {
        const map = L.map(el, { scrollWheelZoom: false }).setView([loc.lat, loc.lng], loc.zoom || 14);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap'
        }).addTo(map);
        L.marker([loc.lat, loc.lng]).addTo(map).bindPopup(loc.name).openPopup();
        // Fix tile sizing now the container is laid out in the DOM
        setTimeout(() => map.invalidateSize(), 100);
    });
}

// Append message element to container (Light Theme Structure)
function appendMessage(role, content, confidence = null, sources = null, locations = null) {
    const chatMsg = document.getElementById('chat-messages');
    if (!chatMsg) return;

    // Remove typing indicator if exists before appending new message
    const indicator = document.getElementById('typing-indicator');
    if (indicator) indicator.remove();

    const messageDiv = document.createElement('div');
    messageDiv.className = `message-row ${role}`;

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'avatar';
    avatarDiv.innerHTML = role === 'bot' ? '<i class="fa-solid fa-robot"></i>' : '';

    const wrapperDiv = document.createElement('div');
    wrapperDiv.className = 'message-content-wrapper';

    const bubbleDiv = document.createElement('div');
    bubbleDiv.className = 'message-bubble';

    // Format bold markdown or linebreaks dynamically
    let formattedText = content
        .replace(/\n/g, '<br>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>');
    
    bubbleDiv.innerHTML = `<p>${formattedText}</p>`;

    wrapperDiv.appendChild(bubbleDiv);

    // Add sources if available (matching the image)
    if (role === 'bot' && sources && sources.length > 0) {
        const sourcesDiv = document.createElement('div');
        sourcesDiv.style.marginTop = '8px';
        sourcesDiv.style.display = 'flex';
        sourcesDiv.style.alignItems = 'center';
        sourcesDiv.style.gap = '8px';
        sourcesDiv.style.flexWrap = 'wrap';
        
        const label = document.createElement('span');
        label.style.fontSize = '12px';
        label.style.color = '#94a3b8';
        label.innerText = 'Nguồn:';
        sourcesDiv.appendChild(label);

        sources.forEach(src => {
            const srcChip = document.createElement('span');
            srcChip.style.background = '#e0f2fe';
            srcChip.style.color = '#0284c7';
            srcChip.style.padding = '4px 8px';
            srcChip.style.borderRadius = '12px';
            srcChip.style.fontSize = '11px';
            srcChip.style.fontWeight = '500';
            srcChip.style.display = 'inline-flex';
            srcChip.style.alignItems = 'center';
            srcChip.style.gap = '4px';
            // clean up source name if it's a file path
            let cleanName = src.name || src.source || "Tài liệu";
            if (cleanName.includes('/')) cleanName = cleanName.split('/').pop();
            cleanName = cleanName.replace('.pdf', '').replace('.txt', '').replace('.md', '');
            
            srcChip.innerHTML = `<i class="fa-regular fa-file-lines"></i> ${cleanName}`;
            sourcesDiv.appendChild(srcChip);
        });
        wrapperDiv.appendChild(sourcesDiv);
    }

    // Add confidence badge for bot responses
    if (role === 'bot' && confidence) {
        const level = confidence.level.toLowerCase();
        const score = Math.round(confidence.score * 100);
        const confBadge = document.createElement('div');
        confBadge.style.fontSize = '10px';
        confBadge.style.marginTop = '4px';
        confBadge.style.color = '#94a3b8';
        confBadge.innerHTML = `<i class="fa-solid fa-shield-halved"></i> Confidence: ${level.toUpperCase()} (${score}%)`;
        wrapperDiv.appendChild(confBadge);
    }

    // Build map panels for any detected Vinpearl locations (bot only)
    const mapEls = role === 'bot' ? buildLocationMaps(wrapperDiv, locations) : [];

    const timeDiv = document.createElement('div');
    timeDiv.className = 'timestamp';
    timeDiv.innerText = formatTime();
    wrapperDiv.appendChild(timeDiv);

    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(wrapperDiv);
    chatMsg.appendChild(messageDiv);

    // Maps must be initialised after they are attached to the DOM
    initLocationMaps(mapEls);

    scrollToBottom();
}

// Initialize Speech Recognition
function initVoiceInput(chatInput, chatForm) {
    const voiceBtn = document.getElementById('voice-btn');
    if (!voiceBtn) return;

    // Check browser support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        console.warn('Web Speech API is not supported in this browser.');
        voiceBtn.style.display = 'none';
        return;
    }

    recognition = new SpeechRecognition();
    recognition.lang = 'vi-VN'; // Default to Vietnamese
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
        isRecording = true;
        voiceBtn.classList.add('recording');
        chatInput.placeholder = 'Đang nghe...';
    };

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        chatInput.value = transcript;
        // Auto-submit after voice input
        chatForm.dispatchEvent(new Event('submit'));
    };

    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        chatInput.placeholder = 'Lỗi thu âm. Vui lòng thử lại...';
        setTimeout(() => {
            chatInput.placeholder = 'Nhập tin nhắn... (đa ngôn ngữ)';
        }, 3000);
    };

    recognition.onend = () => {
        isRecording = false;
        voiceBtn.classList.remove('recording');
        if (chatInput.placeholder === 'Đang nghe...') {
            chatInput.placeholder = 'Nhập tin nhắn... (đa ngôn ngữ)';
        }
    };

    voiceBtn.addEventListener('click', () => {
        if (isRecording) {
            recognition.stop();
        } else {
            // Update lang based on select
            const langSelect = document.querySelector('.lang-select');
            if (langSelect && langSelect.value.includes('EN')) {
                recognition.lang = 'en-US';
            } else {
                recognition.lang = 'vi-VN';
            }
            recognition.start();
        }
    });
}

// All Vinpearl properties for the overview map (mirrors backend registry)
const VINPEARL_PLACES = [
    { name: 'Vinpearl Nha Trang', lat: 12.2145, lng: 109.2962 },
    { name: 'Vinpearl Nam Hội An', lat: 15.7016, lng: 108.3735 },
    { name: 'Vinpearl Phú Quốc', lat: 10.3247, lng: 103.8540 },
    { name: 'Melia Vinpearl Cửa Sót (Hà Tĩnh)', lat: 18.3530, lng: 105.9090 },
    { name: 'Vinpearl Hotel Bắc Ninh', lat: 21.1845, lng: 106.0750 },
    { name: 'Melia Vinpearl Cửa Hội (Nghệ An)', lat: 18.7820, lng: 105.7090 },
    { name: 'Vinpearl Resort & Spa Hạ Long', lat: 20.9470, lng: 107.0735 },
];

let overviewMap = null;

// Map of all Vinpearl locations across Vietnam, shown in the right sidebar.
function initOverviewMap() {
    const el = document.getElementById('overview-map');
    if (!el || overviewMap || !window.L) return;

    overviewMap = L.map(el, { scrollWheelZoom: false }).setView([16.2, 107.5], 5);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap'
    }).addTo(overviewMap);

    const bounds = [];
    VINPEARL_PLACES.forEach(p => {
        L.marker([p.lat, p.lng]).addTo(overviewMap).bindPopup(p.name);
        bounds.push([p.lat, p.lng]);
    });
    overviewMap.fitBounds(bounds, { padding: [30, 30] });

    // Container may have been hidden during init — recompute size once visible
    setTimeout(() => overviewMap.invalidateSize(), 200);
}

// Initialize Chat Module
function initChatView() {
    initOverviewMap();
    if (chatInitialized) return;
    chatInitialized = true;

    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');

    // Initialize Voice Input
    initVoiceInput(chatInput, chatForm);

    // Attachment Input
    const attachBtn = document.getElementById('attach-btn');
    const fileUpload = document.getElementById('chat-file-upload');
    let selectedFile = null;

    if (attachBtn && fileUpload) {
        attachBtn.addEventListener('click', () => {
            fileUpload.click();
        });

        fileUpload.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                selectedFile = e.target.files[0];
                attachBtn.style.color = '#1e3a8a'; // highlight
                chatInput.placeholder = `Đã đính kèm: ${selectedFile.name}`;
            } else {
                selectedFile = null;
                attachBtn.style.color = '#94a3b8';
                chatInput.placeholder = 'Nhập tin nhắn... (đa ngôn ngữ)';
            }
        });
    }

    // Chat submit
    if (chatForm) {
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = chatInput.value.trim();
            if (!text && !selectedFile) return; // Allow empty text if file attached

            // Stop recording if active
            if (isRecording && recognition) {
                recognition.stop();
            }

            // Clear input and file
            chatInput.value = '';
            chatInput.placeholder = 'Nhập tin nhắn... (đa ngôn ngữ)';
            if (attachBtn) attachBtn.style.color = '#94a3b8';
            
            // Append User message
            let msgText = text;
            if (selectedFile) {
                msgText += ` <br><small><i>[Đã đính kèm tệp: ${selectedFile.name}]</i></small>`;
                selectedFile = null; // reset
                if (fileUpload) fileUpload.value = '';
            }
            appendMessage('user', msgText);
            
            // Show Typing indicator
            showTypingIndicator(true);

            try {
                const response = await api.post('/chat', {
                    session_id: getSessionId(),
                    message: text
                });

                showTypingIndicator(false);

                if (response.ok) {
                    appendMessage('bot', response.reply, response.confidence, response.sources, response.locations);
                } else {
                    appendMessage('bot', 'Xin lỗi quý khách, trợ lý gặp lỗi kết nối hệ thống. Xin hãy thử lại.');
                }
            } catch (error) {
                showTypingIndicator(false);
                appendMessage('bot', 'Xin lỗi quý khách, kết nối mạng gặp vấn đề. Vui lòng gửi lại câu hỏi.');
            }
        });
    }

    // Quick Action button listeners
    document.querySelectorAll('.qa-chip').forEach(pill => {
        pill.addEventListener('click', () => {
            const message = pill.getAttribute('data-msg');
            if (chatInput) {
                chatInput.value = message;
                chatForm.dispatchEvent(new Event('submit'));
            }
        });
    });
}
