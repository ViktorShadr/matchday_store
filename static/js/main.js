/**
 * Main JavaScript file for FC Shinnik Store
 * Contains shared utility functions used across the site
 */

// Cookie Banner
(function() {
    const COOKIE_CONSENT_KEY = 'cookie_consent';
    const banner = document.getElementById('cookie-banner');
    const acceptBtn = document.getElementById('cookie-accept');
    const declineBtn = document.getElementById('cookie-decline');

    if (!banner) return;

    // Check if user has already made a choice
    const consent = localStorage.getItem(COOKIE_CONSENT_KEY);
    if (!consent) {
        banner.classList.remove('hidden');
    }

    if (acceptBtn) {
        acceptBtn.addEventListener('click', function() {
            localStorage.setItem(COOKIE_CONSENT_KEY, 'accepted');
            banner.classList.add('hidden');
        });
    }

    if (declineBtn) {
        declineBtn.addEventListener('click', function() {
            localStorage.setItem(COOKIE_CONSENT_KEY, 'declined');
            banner.classList.add('hidden');
        });
    }
})();

/**
 * Get cookie value by name
 * @param {string} name - Cookie name
 * @returns {string|null} Cookie value or null
 */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

/**
 * Get CSRF token from cookie or DOM
 * @returns {string} CSRF token
 */
function getCsrfToken() {
    // First try to find in DOM
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    if (csrfToken) {
        return csrfToken;
    }
    // Fallback to cookie
    return getCookie('csrftoken');
}

/**
 * Show notification toast
 * @param {string} message - Notification message
 * @param {string} type - Notification type: 'success' or 'error'
 * @param {number} duration - Duration in milliseconds (default: 3000)
 */
function showNotification(message, type, duration = 3000) {
    // Remove existing notifications
    const existingNotifications = document.querySelectorAll('.sf-notification');
    existingNotifications.forEach(n => n.remove());

    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : 'success'} position-fixed sf-notification`;
    notification.style.cssText = 'top: 20px; left: 50%; transform: translateX(-50%); z-index: 9999; min-width: 300px; max-width: 500px; text-align: center; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.15);';
    notification.textContent = message;

    document.body.appendChild(notification);

    // Auto-remove after duration
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 300ms ease';
        setTimeout(() => notification.remove(), 300);
    }, duration);
}

/**
 * Update cart counter in header
 * @param {number} count - New cart items count
 */
function updateCartCounter(count) {
    const cartCounter = document.querySelector('.cart-counter');
    if (cartCounter) {
        cartCounter.textContent = count;
        // Add animation
        cartCounter.style.transform = 'scale(1.3)';
        setTimeout(() => {
            cartCounter.style.transition = 'transform 200ms ease';
            cartCounter.style.transform = 'scale(1)';
        }, 100);
    }
}

/**
 * Format price with thousand separators
 * @param {number} price - Price value
 * @returns {string} Formatted price
 */
function formatPrice(price) {
    return new Intl.NumberFormat('ru-RU').format(price);
}

/**
 * Debounce function
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Mini-cart functionality
(function() {
    const cartBtn = document.querySelector('[data-mini-cart-toggle]');
    const miniCart = document.querySelector('.sf-mini-cart');

    if (cartBtn && miniCart) {
        cartBtn.addEventListener('click', function(e) {
            e.preventDefault();
            miniCart.classList.toggle('show');
        });

        // Close when clicking outside
        document.addEventListener('click', function(e) {
            if (!cartBtn.contains(e.target) && !miniCart.contains(e.target)) {
                miniCart.classList.remove('show');
            }
        });
    }
})();

// Quick-add functionality for product cards
(function() {
    document.addEventListener('DOMContentLoaded', function() {
        const quickAddBtns = document.querySelectorAll('.quick-add-btn');

        quickAddBtns.forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();

                const variantId = this.dataset.variantId;
                if (!variantId) return;

                // Disable button during request
                this.disabled = true;
                const originalContent = this.innerHTML;
                this.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

                fetch('/cart/add/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: `variant_id=${variantId}&quantity=1`
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showNotification(data.message, 'success');
                        updateCartCounter(data.cart_total);
                    } else {
                        showNotification(data.error, 'error');
                    }
                })
                .catch(error => {
                    showNotification('Ошибка при добавлении товара', 'error');
                })
                .finally(() => {
                    this.disabled = false;
                    this.innerHTML = originalContent;
                });
            });
        });
    });
})();

// Toast notification system
(function() {
    // Create container if not exists
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'sf-toast-container';
        document.body.appendChild(container);
    }

    // Override showNotification to use toast
    window.showNotification = function(message, type = 'success', title = '') {
        const icons = {
            success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>',
            error: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',
            info: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
        };

        const titles = {
            success: title || 'Успешно',
            error: title || 'Ошибка',
            info: title || 'Информация'
        };

        const toast = document.createElement('div');
        toast.className = `sf-toast ${type}`;
        toast.innerHTML = `
            <div class="sf-toast-icon">${icons[type] || icons.info}</div>
            <div class="sf-toast-content">
                <div class="sf-toast-title">${titles[type]}</div>
                <div class="sf-toast-message">${message}</div>
            </div>
            <button class="sf-toast-close" onclick="this.parentElement.remove()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        `;

        container.appendChild(toast);

        // Auto remove after 4 seconds
        setTimeout(() => {
            toast.classList.add('removing');
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    };
})();

// Scroll to top button
(function() {
    const scrollBtn = document.createElement('button');
    scrollBtn.className = 'sf-scroll-top';
    scrollBtn.setAttribute('aria-label', 'Наверх');
    scrollBtn.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="18 15 12 9 6 15"></polyline>
        </svg>
    `;
    scrollBtn.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    document.body.appendChild(scrollBtn);

    // Show/hide on scroll
    let ticking = false;
    window.addEventListener('scroll', () => {
        if (!ticking) {
            window.requestAnimationFrame(() => {
                scrollBtn.classList.toggle('show', window.scrollY > 300);
                ticking = false;
            });
            ticking = true;
        }
    });
})();

// Confirm toast notification with action buttons
function showConfirmToast(message, onConfirm, onCancel) {
    const container = document.getElementById('toastContainer') || (() => {
        const c = document.createElement('div');
        c.id = 'toastContainer';
        c.className = 'sf-toast-container';
        document.body.appendChild(c);
        return c;
    })();

    const toast = document.createElement('div');
    toast.className = 'sf-toast info';
    toast.style.minWidth = '350px';
    toast.innerHTML = `
        <div class="sf-toast-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
        </div>
        <div class="sf-toast-content">
            <div class="sf-toast-title">Подтвердите действие</div>
            <div class="sf-toast-message">${message}</div>
            <div class="mt-2 d-flex gap-2">
                <button class="btn btn-sm btn-danger confirm-btn">Удалить</button>
                <button class="btn btn-sm btn-outline-secondary cancel-btn">Отмена</button>
            </div>
        </div>
    `;

    container.appendChild(toast);

    const confirmBtn = toast.querySelector('.confirm-btn');
    const cancelBtn = toast.querySelector('.cancel-btn');

    const removeToast = () => {
        toast.classList.add('removing');
        setTimeout(() => toast.remove(), 300);
    };

    confirmBtn.addEventListener('click', () => {
        removeToast();
        if (typeof onConfirm === 'function') onConfirm();
    });

    cancelBtn.addEventListener('click', () => {
        removeToast();
        if (typeof onCancel === 'function') onCancel();
    });

    // Auto remove after 10 seconds if no action
    setTimeout(() => {
        if (toast.parentNode) {
            toast.classList.add('removing');
            setTimeout(() => toast.remove(), 300);
        }
    }, 10000);
}

// Export functions for use in other scripts
window.getCookie = getCookie;
window.getCsrfToken = getCsrfToken;
window.showNotification = showNotification;
window.showConfirmToast = showConfirmToast;
window.updateCartCounter = updateCartCounter;
window.formatPrice = formatPrice;
window.debounce = debounce;
