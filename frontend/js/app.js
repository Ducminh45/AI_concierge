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
function isAuthenticated() { return true; }
function getUser() {
    return {
        username: "staymate_admin",
        full_name: "StayMate Admin",
        role: "admin"
    };
}
function saveAuthState(token, user) {}
function clearAuthState() {
    localStorage.removeItem('rc_session_id');
}

// --- Router ---
const routes = {
    '#chat':     { view: 'chat-page',     auth: false, init: () => initChatView() },
    '#services': { view: 'services-page', auth: false, init: () => loadServicesView() },
    '#admin':    { view: 'admin-page',    auth: false, init: () => loadAdminView() }
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
    const currentHash = window.location.hash || '#chat';

    // Show topbar and navbar on non-chat pages, hide on chat page to match screenshot layout
    if (currentHash === '#chat') {
        if (navbar) navbar.classList.add('hidden');
        if (topbar) topbar.classList.add('hidden');
    } else {
        if (navbar) navbar.classList.remove('hidden');
        if (topbar) topbar.classList.remove('hidden');
    }

    const userNameSpan = document.getElementById('topbar-user-name');
    const servicesTab = document.getElementById('nav-services');
    const adminTab = document.getElementById('nav-admin');

    if (userNameSpan) {
        userNameSpan.innerText = `${user.full_name || user.username} (${user.role.toUpperCase()})`;
    }
    if (servicesTab) servicesTab.classList.remove('hidden');
    if (adminTab) adminTab.classList.remove('hidden');

    // Active nav
    document.querySelectorAll('.nav-link[href^="#"]').forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === currentHash) link.classList.add('active');
    });
}

async function router() {
    const hash = window.location.hash || '#chat';
    const route = routes[hash];
    if (!route) { navigateTo('#chat'); return; }
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
