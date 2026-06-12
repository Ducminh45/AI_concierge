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
        const chatMsg = document.getElementById('chat-history-log');
        if (!chatMsg) return;
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.className = 'message-row bot';
        typingDiv.innerHTML = `
            <div class="avatar"><i class="fa-solid fa-wand-magic-sparkles"></i></div>
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

// Append message element to container (Light Theme Structure)
// Helper to parse location keywords and update map
const locationKeywords = {
    'phú quốc': 'Vinpearl Phu Quoc',
    'nha trang': 'Vinpearl Nha Trang',
    'nam hội an': 'Vinpearl Nam Hoi An',
    'hội an': 'Vinpearl Nam Hoi An',
    'hà tĩnh': 'Melia Vinpearl Ha Tinh',
    'cửa sót': 'Melia Vinpearl Cua Sot',
    'nghệ an': 'Melia Vinpearl Cua Hoi',
    'cửa hội': 'Melia Vinpearl Cua Hoi',
    'bắc ninh': 'Melia Vinpearl Bac Ninh',
    'quảng ninh': 'Vinpearl Resort & Spa Ha Long',
    'hạ long': 'Vinpearl Resort & Spa Ha Long',
    'đảo rều': 'Vinpearl Resort & Spa Ha Long'
};

function detectLocationAndUpdateMap(text) {
    const lowerText = text.toLowerCase();
    for (const [keyword, searchQuery] of Object.entries(locationKeywords)) {
        if (lowerText.includes(keyword)) {
            updateMap(searchQuery);
            break;
        }
    }
}

function updateMap(query) {
    const mapIframe = document.getElementById('map-iframe');
    if (mapIframe) {
        mapIframe.src = `https://maps.google.com/maps?q=${encodeURIComponent(query)}&t=&z=14&ie=UTF8&iwloc=&output=embed`;
    }
}

// Helper to extract image markdown tags and update right side gallery
function extractImagesAndPopulateGallery(text) {
    const regex = /!\[(.*?)\]\((.*?)\)/g;
    const images = [];
    let match;
    while ((match = regex.exec(text)) !== null) {
        images.push({
            alt: match[1] || 'Vinpearl Image',
            url: match[2]
        });
    }
    
    if (images.length > 0) {
        updateGallery(images);
    }
}

function updateGallery(images) {
    const imgLeft = document.querySelector('#gallery-img-left img');
    const imgRightTop = document.querySelector('#gallery-img-right-top img');
    const overlayRightTop = document.querySelector('#gallery-img-right-top .image-overlay-text');
    const imgRightBottom = document.querySelector('#gallery-img-right-bottom img');
    
    if (images[0] && imgLeft) {
        imgLeft.src = images[0].url;
        imgLeft.alt = images[0].alt;
    }
    if (images[1] && imgRightTop) {
        imgRightTop.src = images[1].url;
        imgRightTop.alt = images[1].alt;
        if (overlayRightTop) {
            overlayRightTop.innerText = images[1].alt;
            overlayRightTop.style.display = 'block';
        }
    } else if (imgRightTop) {
        if (overlayRightTop) overlayRightTop.style.display = 'none';
    }
    if (images[2] && imgRightBottom) {
        imgRightBottom.src = images[2].url;
        imgRightBottom.alt = images[2].alt;
    }
}

function updateWeatherUI(toolResult) {
    const locTitle = document.getElementById('weather-location-title');
    const container = document.getElementById('weather-forecast-container');
    const tabWeatherBtn = document.getElementById('tab-weather-btn');
    const mediaWeatherContent = document.getElementById('media-weather-content');
    
    if (!toolResult || !toolResult.forecast || !container) return;
    
    // Switch tab to Weather automatically
    const tabGalleryBtn = document.getElementById('tab-gallery-btn');
    const tabMapBtn = document.getElementById('tab-map-btn');
    const mediaGalleryContent = document.getElementById('media-gallery-content');
    const mediaMapContent = document.getElementById('media-map-content');
    
    [tabGalleryBtn, tabMapBtn, tabWeatherBtn].forEach(btn => {
        if (btn) btn.classList.remove('active');
    });
    [mediaGalleryContent, mediaMapContent, mediaWeatherContent].forEach(c => {
        if (c) c.classList.add('hidden');
    });
    if (tabWeatherBtn) tabWeatherBtn.classList.add('active');
    if (mediaWeatherContent) mediaWeatherContent.classList.remove('hidden');

    // Update location title
    if (locTitle) {
        locTitle.innerText = `Thời tiết: ${toolResult.location}`;
    }
    
    const getIconClass = (iconCode) => {
        const icon = iconCode.substring(0, 2);
        switch (icon) {
            case '01': return 'fa-sun';
            case '02': return 'fa-cloud-sun';
            case '03':
            case '04': return 'fa-cloud';
            case '09': return 'fa-cloud-showers-heavy';
            case '10': return 'fa-cloud-sun-rain';
            case '11': return 'fa-cloud-bolt';
            case '13': return 'fa-snowflake';
            case '50': return 'fa-smog';
            default: return 'fa-cloud-sun';
        }
    };
    
    const formatDayName = (dateStr) => {
        try {
            const date = new Date(dateStr);
            const today = new Date();
            if (date.toDateString() === today.toDateString()) {
                return 'Hôm nay';
            }
            const tomorrow = new Date(today);
            tomorrow.setDate(tomorrow.getDate() + 1);
            if (date.toDateString() === tomorrow.toDateString()) {
                return 'Ngày mai';
            }
            const locale = window.location.search.includes('lang=en') ? 'en-US' : 'vi-VN';
            return date.toLocaleDateString(locale, { weekday: 'long' });
        } catch (e) {
            return dateStr;
        }
    };
    
    const formatDateShort = (dateStr) => {
        try {
            const date = new Date(dateStr);
            const locale = window.location.search.includes('lang=en') ? 'en-US' : 'vi-VN';
            return date.toLocaleDateString(locale, { day: '2-digit', month: '2-digit' });
        } catch (e) {
            return '';
        }
    };

    container.innerHTML = '';
    
    toolResult.forecast.forEach(day => {
        const dayName = formatDayName(day.date);
        const dateShort = formatDateShort(day.date);
        const iconClass = getIconClass(day.icon);
        
        const row = document.createElement('div');
        row.className = 'weather-row';
        row.innerHTML = `
            <div class="weather-row-day">
                <div>${dayName}</div>
                <div style="font-size: 11px; font-weight: normal; color: #64748b; margin-top: 2px;">${dateShort}</div>
            </div>
            <div class="weather-row-icon">
                <i class="fa-solid ${iconClass}"></i>
            </div>
            <div class="weather-row-desc">${day.description}</div>
            <div class="weather-row-temp">
                <span class="temp-max">${Math.round(day.temp_max)}°C</span>
                <span style="color: #475569; font-size: 11px;">/</span>
                <span class="temp-min">${Math.round(day.temp_min)}°C</span>
            </div>
            <div class="weather-details-mini">
                <span><i class="fa-solid fa-droplet"></i>Độ ẩm: ${day.humidity}%</span>
                <span><i class="fa-solid fa-wind"></i>Gió: ${day.wind_speed} m/s</span>
            </div>
        `;
        container.appendChild(row);
    });
}

// Transition from welcome screen to chat log layout
function ensureChatHistoryVisible() {
    const welcomeScreen = document.getElementById('chat-welcome-screen');
    const historyLog = document.getElementById('chat-history-log');
    if (welcomeScreen && !welcomeScreen.classList.contains('hidden')) {
        welcomeScreen.classList.add('hidden');
    }
    if (historyLog && historyLog.classList.contains('hidden')) {
        historyLog.classList.remove('hidden');
    }
}

// Append message element to container
function appendMessage(role, content, confidence = null, sources = null, toolName = null, toolResult = null) {
    const chatMsg = document.getElementById('chat-history-log');
    if (!chatMsg) return;

    ensureChatHistoryVisible();

    // Remove typing indicator if exists before appending new message
    const indicator = document.getElementById('typing-indicator');
    if (indicator) indicator.remove();

    const messageDiv = document.createElement('div');
    messageDiv.className = `message-row ${role}`;

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'avatar';
    avatarDiv.innerHTML = role === 'bot' ? '<i class="fa-solid fa-wand-magic-sparkles"></i>' : '';

    const wrapperDiv = document.createElement('div');
    wrapperDiv.className = 'message-content-wrapper';

    const bubbleDiv = document.createElement('div');
    bubbleDiv.className = 'message-bubble';

    // Format bold markdown, linebreaks, images, and links dynamically
    let formattedText = content
        .replace(/!\[(.*?)\]\((.*?)\)/g, '<img src="$2" alt="$1" class="chat-img" style="max-width: 100%; border-radius: 12px; margin-top: 8px; display: block; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">')
        .replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" style="color: #6E5339; text-decoration: underline; font-weight: 600;">$1</a>')
        .replace(/\n/g, '<br>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>');
    
    bubbleDiv.innerHTML = `<p>${formattedText}</p>`;

    // Inline Chat Weather Card
    if (role === 'bot' && toolName === 'get_weather' && toolResult && toolResult.ok) {
        const forecast = toolResult.forecast || [];
        const lat = toolResult.lat || 10.29877;
        const lon = toolResult.lon || 103.91916;
        const latDir = lat >= 0 ? 'N' : 'S';
        const lonDir = lon >= 0 ? 'E' : 'W';
        const formattedCoords = `Kinh độ: ${Math.abs(lon).toFixed(5)}°${lonDir}, Vĩ độ: ${Math.abs(lat).toFixed(5)}°${latDir}`;
        
        // Get today's temperature (average of min and max)
        const todayForecast = forecast[0] || {};
        const todayTemp = todayForecast.temp_max !== undefined ? Math.round((todayForecast.temp_max + todayForecast.temp_min) / 2) : 28;
        const mainIconCode = todayForecast.icon || '02d';
        
        const getIconClass = (iconCode) => {
            const icon = iconCode.substring(0, 2);
            switch (icon) {
                case '01': return 'fa-sun';
                case '02': return 'fa-cloud-sun';
                case '03':
                case '04': return 'fa-cloud';
                case '09': return 'fa-cloud-showers-heavy';
                case '10': return 'fa-cloud-sun-rain';
                case '11': return 'fa-cloud-bolt';
                case '13': return 'fa-snowflake';
                case '50': return 'fa-smog';
                default: return 'fa-cloud-sun';
            }
        };
        
        const formatInlineDayName = (dateStr) => {
            try {
                const date = new Date(dateStr);
                const today = new Date();
                if (date.toDateString() === today.toDateString()) {
                    return 'Hôm<br>nay';
                }
                const tomorrow = new Date(today);
                tomorrow.setDate(tomorrow.getDate() + 1);
                if (date.toDateString() === tomorrow.toDateString()) {
                    return 'Ngày<br>mai';
                }
                const locale = window.location.search.includes('lang=en') ? 'en-US' : 'vi-VN';
                let dayName = date.toLocaleDateString(locale, { weekday: 'long' });
                return dayName;
            } catch (e) {
                return dateStr;
            }
        };

        const mainIconClass = getIconClass(mainIconCode);
        
        let forecastHTML = '';
        forecast.forEach(day => {
            const dayName = formatInlineDayName(day.date);
            const dayIconClass = getIconClass(day.icon);
            forecastHTML += `
                <div class="chat-weather-day-col">
                    <div class="chat-weather-day-name">${dayName}</div>
                    <div class="chat-weather-day-icon"><i class="fa-solid ${dayIconClass}"></i></div>
                    <div class="chat-weather-day-temp">
                        <strong>${Math.round(day.temp_max)}°</strong>${Math.round(day.temp_min)}°
                    </div>
                </div>
            `;
        });

        const weatherCardDiv = document.createElement('div');
        weatherCardDiv.className = 'chat-weather-card';
        weatherCardDiv.innerHTML = `
            <div class="chat-weather-top">
                <div class="chat-weather-left">
                    <div class="chat-weather-main-icon">
                        <i class="fa-solid ${mainIconClass}"></i>
                    </div>
                    <div class="chat-weather-temp-large">${todayTemp}°C</div>
                </div>
                <div class="chat-weather-right">
                    <div class="chat-weather-title">Dự báo thời tiết</div>
                    <div class="chat-weather-coords">${formattedCoords}</div>
                </div>
            </div>
            <div class="chat-weather-divider"></div>
            <div class="chat-weather-forecast">
                ${forecastHTML}
            </div>
        `;
        bubbleDiv.appendChild(weatherCardDiv);
    }

    wrapperDiv.appendChild(bubbleDiv);

    // Extract images and update gallery if bot replies
    if (role === 'bot') {
        extractImagesAndPopulateGallery(content);
        detectLocationAndUpdateMap(content);
    }

    // Add sources if available
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
            srcChip.style.background = '#f5f5f5';
            srcChip.style.color = '#6E5339';
            srcChip.style.padding = '4px 8px';
            srcChip.style.borderRadius = '12px';
            srcChip.style.fontSize = '11px';
            srcChip.style.fontWeight = '500';
            srcChip.style.display = 'inline-flex';
            srcChip.style.alignItems = 'center';
            srcChip.style.gap = '4px';
            srcChip.style.border = '1px solid #e5e5e5';
            
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
        confBadge.style.color = '#a39695';
        confBadge.innerHTML = `<i class="fa-solid fa-shield-halved"></i> Độ chính xác: ${level.toUpperCase()} (${score}%)`;
        wrapperDiv.appendChild(confBadge);
    }

    const timeDiv = document.createElement('div');
    timeDiv.className = 'timestamp';
    timeDiv.innerText = formatTime();
    wrapperDiv.appendChild(timeDiv);

    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(wrapperDiv);
    chatMsg.appendChild(messageDiv);
    
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
        chatForm.dispatchEvent(new Event('submit'));
    };

    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        chatInput.placeholder = 'Lỗi thu âm. Vui lòng thử lại...';
        setTimeout(() => {
            chatInput.placeholder = 'Nhập tin nhắn của bạn tại đây...';
        }, 3000);
    };

    recognition.onend = () => {
        isRecording = false;
        voiceBtn.classList.remove('recording');
        if (chatInput.placeholder === 'Đang nghe...') {
            chatInput.placeholder = 'Nhập tin nhắn của bạn tại đây...';
        }
    };

    voiceBtn.addEventListener('click', () => {
        if (isRecording) {
            recognition.stop();
        } else {
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

// Initialize Chat Module
function initChatView() {
    if (chatInitialized) return;
    chatInitialized = true;

    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');

    // Initialize Voice Input
    initVoiceInput(chatInput, chatForm);

    // Attachment Input handling
    const attachmentBtn = document.getElementById('attachment-btn');
    const attachmentInput = document.getElementById('attachment-file-input');
    if (attachmentBtn && attachmentInput) {
        attachmentBtn.addEventListener('click', () => {
            attachmentInput.click();
        });
        attachmentInput.addEventListener('change', () => {
            if (attachmentInput.files.length > 0) {
                const file = attachmentInput.files[0];
                alert(`Đã đính kèm tệp: ${file.name}`);
            }
        });
    }

    // Media Tabs toggling
    const tabGalleryBtn = document.getElementById('tab-gallery-btn');
    const tabMapBtn = document.getElementById('tab-map-btn');
    const tabWeatherBtn = document.getElementById('tab-weather-btn');
    const mediaGalleryContent = document.getElementById('media-gallery-content');
    const mediaMapContent = document.getElementById('media-map-content');
    const mediaWeatherContent = document.getElementById('media-weather-content');

    const switchTab = (activeBtn, showContent) => {
        [tabGalleryBtn, tabMapBtn, tabWeatherBtn].forEach(btn => {
            if (btn) btn.classList.remove('active');
        });
        [mediaGalleryContent, mediaMapContent, mediaWeatherContent].forEach(c => {
            if (c) c.classList.add('hidden');
        });
        if (activeBtn) activeBtn.classList.add('active');
        if (showContent) showContent.classList.remove('hidden');
    };

    if (tabGalleryBtn && mediaGalleryContent) {
        tabGalleryBtn.addEventListener('click', () => switchTab(tabGalleryBtn, mediaGalleryContent));
    }
    if (tabMapBtn && mediaMapContent) {
        tabMapBtn.addEventListener('click', () => switchTab(tabMapBtn, mediaMapContent));
    }
    if (tabWeatherBtn && mediaWeatherContent) {
        tabWeatherBtn.addEventListener('click', () => switchTab(tabWeatherBtn, mediaWeatherContent));
    }

    // Chat submit
    if (chatForm) {
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = chatInput.value.trim();
            if (!text) return;

            // Stop recording if active
            if (isRecording && recognition) {
                recognition.stop();
            }

            // Detect user keywords to update map even before bot answers
            detectLocationAndUpdateMap(text);

            // Clear input
            chatInput.value = '';
            chatInput.placeholder = 'Nhập tin nhắn của bạn tại đây...';
            
            // Append User message
            appendMessage('user', text);
            
            // Show Typing indicator
            showTypingIndicator(true);

            try {
                const response = await api.post('/chat', {
                    session_id: getSessionId(),
                    message: text
                });

                showTypingIndicator(false);

                if (response && (response.ok || response.reply)) {
                    appendMessage('bot', response.reply, response.confidence, response.sources, response.tool_name, response.tool_result);
                    if (response.tool_name === 'get_weather' && response.tool_result && response.tool_result.ok) {
                        updateWeatherUI(response.tool_result);
                    }
                } else {
                    appendMessage('bot', 'Xin lỗi quý khách, trợ lý gặp lỗi kết nối hệ thống. Xin hãy thử lại.');
                }
            } catch (error) {
                showTypingIndicator(false);
                appendMessage('bot', 'Xin lỗi quý khách, kết nối mạng gặp vấn đề. Vui lòng gửi lại câu hỏi.');
            }
        });
    }

    // Suggestion chips listeners
    document.querySelectorAll('.suggestion-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const message = chip.getAttribute('data-msg');
            if (chatInput && chatForm) {
                chatInput.value = message;
                chatForm.dispatchEvent(new Event('submit'));
            }
        });
    });
}
