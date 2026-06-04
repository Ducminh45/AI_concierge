/* ==========================================================================
   ADMINISTRATIVE DASHBOARD — ADMIN.JS
   ========================================================================== */

let adminInitialized = false;

// Refresh dashboard data
async function loadAdminView() {
    await Promise.all([
        loadAdminStats(),
        loadAllServiceRequests(),
        loadUsersList()
    ]);

    if (adminInitialized) return;
    adminInitialized = true;

    const refreshBtn = document.getElementById('refresh-admin-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadAdminView);
    }
}

// Fetch dashboard stats
async function loadAdminStats() {
    try {
        const usersData = await api.get('/api/v1/users');
        const reqsData = await api.get('/api/v1/service-requests?all=true');

        if (usersData.ok && reqsData.ok) {
            const usersCount = usersData.users.length;
            const requests = reqsData.requests;

            const pending = requests.filter(r => r.status === 'pending').length;
            const completed = requests.filter(r => r.status === 'completed').length;

            document.getElementById('stat-total-users').innerText = usersCount;
            document.getElementById('stat-pending-requests').innerText = pending;
            document.getElementById('stat-completed-requests').innerText = completed;
        }
    } catch (error) {
        console.error('Failed to load admin stats:', error);
    }
}

// Load and render all service requests
async function loadAllServiceRequests() {
    const tbody = document.getElementById('admin-requests-tbody');
    if (!tbody) return;

    try {
        const data = await api.get('/api/v1/service-requests?all=true');
        if (data.ok && data.requests) {
            tbody.innerHTML = '';
            
            if (data.requests.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" class="text-center">Chưa có yêu cầu nào được gửi.</td></tr>';
                return;
            }

            data.requests.forEach(req => {
                const tr = document.createElement('tr');
                
                const selectHtml = `
                    <select class="status-select" data-id="${req.id}">
                        <option value="pending" ${req.status === 'pending' ? 'selected' : ''}>Chờ xử lý</option>
                        <option value="in_progress" ${req.status === 'in_progress' ? 'selected' : ''}>Đang xử lý</option>
                        <option value="completed" ${req.status === 'completed' ? 'selected' : ''}>Hoàn thành</option>
                        <option value="cancelled" ${req.status === 'cancelled' ? 'selected' : ''}>Đã hủy</option>
                    </select>
                `;

                tr.innerHTML = `
                    <td><strong>#${req.id}</strong></td>
                    <td>${req.guest_name}</td>
                    <td>Phòng ${req.room_number || 'N/A'}</td>
                    <td>${req.resort_name || 'N/A'}</td>
                    <td><span class="gold-color">${req.service_type}</span></td>
                    <td><div style="max-width: 250px; white-space: normal;">${req.details}</div></td>
                    <td><span class="status-badge ${req.status}">${req.status.toUpperCase()}</span></td>
                    <td>${selectHtml}</td>
                `;
                tbody.appendChild(tr);
            });

            // Add Event Listeners for status changes
            document.querySelectorAll('.status-select').forEach(select => {
                select.addEventListener('change', async (e) => {
                    const reqId = e.target.getAttribute('data-id');
                    const newStatus = e.target.value;

                    try {
                        const res = await api.put(`/api/v1/service-requests/${reqId}/status`, {
                            status: newStatus
                        });

                        if (res.ok) {
                            // Reload Dashboard to reflect updates
                            await loadAdminView();
                        }
                    } catch (error) {
                        alert(error.message || 'Không thể cập nhật trạng thái yêu cầu.');
                        // Revert change
                        loadAdminView();
                    }
                });
            });

        }
    } catch (error) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center error-msg">Không thể tải danh sách yêu cầu.</td></tr>';
    }
}

// Load and render user management list
async function loadUsersList() {
    const tbody = document.getElementById('admin-users-tbody');
    if (!tbody) return;

    try {
        const data = await api.get('/api/v1/users');
        if (data.ok && data.users) {
            tbody.innerHTML = '';

            data.users.forEach(u => {
                const tr = document.createElement('tr');
                
                const isSelf = u.username.toLowerCase() === getUser().username.toLowerCase();
                
                const selectHtml = isSelf ? 
                    `<span class="text-muted">Chính bạn (Self)</span>` : 
                    `
                    <select class="role-select" data-username="${u.username}">
                        <option value="guest" ${u.role === 'guest' ? 'selected' : ''}>Guest (Khách)</option>
                        <option value="staff" ${u.role === 'staff' ? 'selected' : ''}>Staff (Nhân viên)</option>
                        <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin (Quản trị)</option>
                    </select>
                `;

                tr.innerHTML = `
                    <td>${u.id}</td>
                    <td><strong>${u.username}</strong></td>
                    <td>${u.full_name || 'N/A'}</td>
                    <td><span class="role-badge ${u.role}">${u.role}</span></td>
                    <td>${selectHtml}</td>
                `;
                tbody.appendChild(tr);
            });

            // Add Event Listeners for role changes
            document.querySelectorAll('.role-select').forEach(select => {
                select.addEventListener('change', async (e) => {
                    const username = e.target.getAttribute('data-username');
                    const newRole = e.target.value;

                    try {
                        const res = await api.put(`/api/v1/users/${username}/role`, {
                            role: newRole
                        });

                        if (res.ok) {
                            await loadAdminView();
                        }
                    } catch (error) {
                        alert(error.message || 'Không thể cập nhật quyền người dùng.');
                        loadAdminView();
                    }
                });
            });
        }
    } catch (error) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center error-msg">Không thể tải danh sách người dùng.</td></tr>';
    }
}
