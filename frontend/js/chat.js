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

// Append message element to container (Light Theme Structure)
function appendMessage(role, content, confidence = null, sources = null) {
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

    // Format bold markdown, linebreaks, images, and links dynamically
    let formattedText = content
        .replace(/!\[(.*?)\]\((.*?)\)/g, '<img src="$2" alt="$1" class="chat-img" style="max-width: 100%; border-radius: 8px; margin-top: 8px; display: block; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">')
        .replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" style="color: #0284c7; text-decoration: underline; font-weight: 500;">$1</a>')
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

// Initialize Chat Module
function initChatView() {
    if (chatInitialized) return;
    chatInitialized = true;

    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');

    // Initialize Voice Input
    initVoiceInput(chatInput, chatForm);

    // Attachment Input removed

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

            // Clear input
            chatInput.value = '';
            chatInput.placeholder = 'Nhập tin nhắn... (đa ngôn ngữ)';
            
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
                    appendMessage('bot', response.reply, response.confidence, response.sources);
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
