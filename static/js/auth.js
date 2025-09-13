document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('login-form');
    const signupForm = document.getElementById('signup-form');
    const alertContainer = document.getElementById('alert-container');

    const showAlert = (message, type = 'danger') => {
        const wrapper = document.createElement('div');
        wrapper.innerHTML = [
            `<div class="alert alert-${type} alert-dismissible" role="alert">`,
            `   <div>${message}</div>`,
            '   <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>',
            '</div>'
        ].join('');
        alertContainer.innerHTML = '';
        alertContainer.append(wrapper);
    };

    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const mobile = document.getElementById('mobile').value;
            const password = document.getElementById('password').value;

            try {
                const response = await fetch('/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ mobile, password })
                });

                const data = await response.json();

                if (response.ok) {
                    showAlert(data.message, 'success');
                    window.location.href = '/dashboard';
                } else {
                    showAlert(data.message || 'An error occurred.');
                }
            } catch (error) {
                showAlert('Could not connect to the server.');
            }
        });
    }

    if (signupForm) {
        signupForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = document.getElementById('name').value;
            const mobile = document.getElementById('mobile').value;
            const password = document.getElementById('password').value;

            try {
                const response = await fetch('/signup', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ name, mobile, password })
                });

                const data = await response.json();

                if (response.ok) {
                    showAlert(data.message, 'success');
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 2000);
                } else {
                    showAlert(data.message || 'An error occurred.');
                }
            } catch (error) {
                showAlert('Could not connect to the server.');
            }
        });
    }
});