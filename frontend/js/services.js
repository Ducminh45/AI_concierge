/* ==========================================================================
   CONCIERGE SERVICES LOGIC — SERVICES.JS
   ========================================================================== */

let servicesInitialized = false;

// Format dates nicely
function formatDateString(isoString) {
    if (!isoString) return '';
    try {
        const date = new Date(isoString);
        return date.toLocaleString('vi-VN', {
            hour: '2-digit',
            minute: '2-digit',
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
    } catch (e) {
        return isoString;
    }
}

// Fetch and render historical service requests
async function loadServiceHistory() {
    const historyList = document.getElementById('services-history-list');
    if (!historyList) return;

    try {
        const data = await api.get('/api/v1/service-requests');
        if (data.ok && data.requests && data.requests.length > 0) {
            historyList.innerHTML = '';
            data.requests.forEach(req => {
                const card = document.createElement('div');
                card.className = 'request-card';

                const statusText = {
                    'pending': 'Chờ xử lý',
                    'in_progress': 'Đang thực hiện',
                    'completed': 'Hoàn thành',
                    'cancelled': 'Đã hủy'
                }[req.status] || req.status;

                card.innerHTML = `
                    <div class="request-card-header">
                        <div>
                            <div class="request-type"><i class="fa-solid fa-square-poll-horizontal"></i> ${req.service_type}</div>
                            <div class="request-resort">${req.resort_name} (Phòng ${req.room_number})</div>
                        </div>
                        <span class="status-badge ${req.status}">${statusText}</span>
                    </div>
                    <div class="request-details">${req.details}</div>
                    <div class="request-card-footer">
                        <span>Yêu cầu #${req.id}</span>
                        <span>${formatDateString(req.created_at)}</span>
                    </div>
                `;
                historyList.appendChild(card);
            });
        } else {
            historyList.innerHTML = '<div class="no-history">Chưa có yêu cầu nào được gửi. / No service requests found.</div>';
        }
    } catch (error) {
        console.error('Failed to load services history:', error);
        historyList.innerHTML = '<div class="error-msg">Không thể tải lịch sử dịch vụ.</div>';
    }
}

// Initializing Services Module
function loadServicesView() {
    loadServiceHistory();

    if (servicesInitialized) return;
    servicesInitialized = true;

    const requestForm = document.getElementById('service-request-form');
    const successMsg = document.getElementById('service-success-msg');
    const errorMsg = document.getElementById('service-error-msg');

    if (requestForm) {
        requestForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            successMsg.classList.add('hidden');
            errorMsg.classList.add('hidden');

            const resort = document.getElementById('srv-resort').value;
            const room = document.getElementById('srv-room').value.trim();
            const serviceType = document.getElementById('srv-type').value;
            const details = document.getElementById('srv-details').value.trim();

            try {
                const response = await api.post('/api/v1/service-requests', {
                    resort_name: resort,
                    room_number: room,
                    service_type: serviceType,
                    details: details
                });

                if (response.ok) {
                    successMsg.innerText = 'Gửi yêu cầu dịch vụ thành công! / Request submitted successfully!';
                    successMsg.classList.remove('hidden');
                    requestForm.reset();
                    
                    // Reload history
                    await loadServiceHistory();
                }
            } catch (error) {
                errorMsg.innerText = error.message || 'Không thể gửi yêu cầu dịch vụ. Vui lòng liên hệ lễ tân.';
                errorMsg.classList.remove('hidden');
            }
        });
    }
}
