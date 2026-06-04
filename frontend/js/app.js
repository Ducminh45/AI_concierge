/* ==========================================================================
   SPA CORE MODULE — APP.JS
   ========================================================================== */

// --- API Client ---
class APIClient {
    constructor(baseURL = '') { this.baseURL = baseURL; }
    getHeaders() {
        const h = { 'Content-Type': 'application/json' };
        const t = localStorage.getItem('rc_token');
        if (t) h['Authorization'] = `Bearer ${t}`;
        return h;
    }
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const merged = { ...options, headers: { ...this.getHeaders(), ...options.headers } };
        try {
            const res = await fetch(url, merged);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'An error occurred');
            return data;
        } catch (err) { console.error(`API Error on ${endpoint}:`, err); throw err; }
    }
    get(ep) { return this.request(ep, { method: 'GET' }); }
    post(ep, body) { return this.request(ep, { method: 'POST', body: JSON.stringify(body) }); }
    put(ep, body) { return this.request(ep, { method: 'PUT', body: JSON.stringify(body) }); }
    delete(ep) { return this.request(ep, { method: 'DELETE' }); }
}
const api = new APIClient();

// --- Auth State ---
function isAuthenticated() { return !!localStorage.getItem('rc_token'); }
function getUser() {
    const s = localStorage.getItem('rc_user');
    return s ? JSON.parse(s) : null;
}
function saveAuthState(token, user) {
    localStorage.setItem('rc_token', token);
    localStorage.setItem('rc_user', JSON.stringify(user));
}
function clearAuthState() {
    localStorage.removeItem('rc_token');
    localStorage.removeItem('rc_user');
    localStorage.removeItem('rc_session_id');
}

// --- Router ---
const routes = {
    '#login':    { view: 'login-page',    auth: false, init: () => {} },
    '#register': { view: 'register-page', auth: false, init: () => {} },
    '#chat':     { view: 'chat-page',     auth: true,  init: () => initChatView() },
    '#services': { view: 'services-page', auth: true,  init: () => loadServicesView() },
    '#admin':    { view: 'admin-page',    auth: true,  init: () => loadAdminView() }
};
function navigateTo(hash) { window.location.hash = hash; }

function showPage(pageId) {
    document.querySelectorAll('.page-view').forEach(v => v.classList.add('hidden'));
    const el = document.getElementById(pageId);
    if (el) el.classList.remove('hidden');
}

function updateNavigation() {
    const navbar = document.getElementById('navbar');
    const topbar = document.getElementById('topbar');
    const user = getUser();

    if (!isAuthenticated() || !user) {
        navbar.classList.add('hidden');
        topbar.classList.add('hidden');
        return;
    }

    navbar.classList.remove('hidden');
    topbar.classList.remove('hidden');

    // Topbar user name
    const un = document.getElementById('topbar-user-name');
    if (un) un.innerText = `${user.full_name || user.username} (${user.role.toUpperCase()})`;

    // Hide login link when authenticated
    const ll = document.getElementById('topbar-login-link');
    if (ll) ll.style.display = 'none';

    // Admin tab
    const adminTab = document.getElementById('nav-admin');
    if (user.role === 'admin' || user.role === 'staff') {
        adminTab.classList.remove('hidden');
    } else {
        adminTab.classList.add('hidden');
    }

    // Active nav
    const currentHash = window.location.hash || '#chat';
    document.querySelectorAll('.nav-link[href^="#"]').forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === currentHash) link.classList.add('active');
    });
}

async function router() {
    const hash = window.location.hash || '#chat';
    const route = routes[hash];
    if (!route) { navigateTo('#chat'); return; }
    if (route.auth && !isAuthenticated()) { navigateTo('#login'); return; }
    if (!route.auth && isAuthenticated()) { navigateTo('#chat'); return; }
    showPage(route.view);
    updateNavigation();
    route.init();
}

// --- Bootstrap ---
document.addEventListener('DOMContentLoaded', () => {
    // Nav clicks
    document.querySelectorAll('.nav-link[href^="#"]').forEach(link => {
        link.addEventListener('click', () => navigateTo(link.getAttribute('href')));
    });

    // Book now
    const bookBtn = document.getElementById('btn-book-now');
    if (bookBtn) bookBtn.addEventListener('click', e => { e.preventDefault(); navigateTo('#chat'); });

    // Logout
    document.getElementById('logout-btn').addEventListener('click', () => {
        clearAuthState();
        navigateTo('#login');
    });

    // Mobile hamburger toggle
    const hamburger = document.getElementById('nav-hamburger-btn');
    if (hamburger) {
        hamburger.addEventListener('click', () => {
            const left = document.querySelector('.nav-left');
            const right = document.querySelector('.nav-right');
            if (left) left.classList.toggle('open');
            if (right) right.classList.toggle('open');
        });
    }

    // Router
    window.addEventListener('hashchange', router);
    router();
});
