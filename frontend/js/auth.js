/* ==========================================================================
   AUTHENTICATION LOGIC — AUTH.JS
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    const loginError = document.getElementById('login-error');
    const registerError = document.getElementById('register-error');

    // --- Login Form Handler ---
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            loginError.classList.add('hidden');
            
            const username = document.getElementById('login-username').value.trim();
            const password = document.getElementById('login-password').value;

            try {
                const response = await api.post('/api/v1/auth/login', {
                    username: username,
                    password: password
                });

                if (response.ok && response.token) {
                    saveAuthState(response.token, response.user);
                    // Clear fields
                    loginForm.reset();
                    // Navigate to home chat
                    navigateTo('#chat');
                }
            } catch (error) {
                loginError.innerText = error.message || 'Đăng nhập thất bại. Vui lòng kiểm tra lại thông tin.';
                loginError.classList.remove('hidden');
            }
        });
    }

    // --- Register Form Handler ---
    if (registerForm) {
        registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            registerError.classList.add('hidden');

            const username = document.getElementById('register-username').value.trim();
            const fullName = document.getElementById('register-fullname').value.trim();
            const email = document.getElementById('register-email').value.trim();
            const password = document.getElementById('register-password').value;

            try {
                const response = await api.post('/api/v1/auth/register', {
                    username: username,
                    password: password,
                    email: email || null,
                    full_name: fullName || null
                });

                if (response.ok && response.token) {
                    saveAuthState(response.token, response.user);
                    // Clear fields
                    registerForm.reset();
                    // Navigate to home chat
                    navigateTo('#chat');
                }
            } catch (error) {
                registerError.innerText = error.message || 'Đăng ký thất bại. Vui lòng kiểm tra lại thông tin đăng ký.';
                registerError.classList.remove('hidden');
            }
        });
    }
});
