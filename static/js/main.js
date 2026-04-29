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

// Product card sliders (Swiper) + lightbox (Fancybox)
(function() {
    const cardSwipers = document.querySelectorAll('[data-sf-product-swiper]');

    if (cardSwipers.length && typeof window.Swiper === 'function') {
        cardSwipers.forEach((swiperEl) => {
            const paginationEl = swiperEl.querySelector('.swiper-pagination');
            if (!paginationEl) {
                return;
            }

            new window.Swiper(swiperEl, {
                slidesPerView: 1,
                spaceBetween: 0,
                speed: 360,
                pagination: {
                    el: paginationEl,
                    clickable: true,
                },
            });
        });
    }

    if (window.Fancybox && typeof window.Fancybox.bind === 'function') {
        window.Fancybox.bind('[data-fancybox^="product-card-"]', {
            groupAll: false,
        });
    }
})();

// Product media slider (detail page)
(function() {
    const sliderRoots = document.querySelectorAll('[data-sf-slider]');
    if (!sliderRoots.length) {
        return;
    }

    sliderRoots.forEach((root) => {
        const track = root.querySelector('[data-sf-slider-track]');
        if (!track) {
            return;
        }

        const slides = Array.from(track.querySelectorAll('[data-sf-slider-slide]'));
        if (slides.length < 2) {
            return;
        }

        const controls = Array.from(root.querySelectorAll('[data-sf-slider-to]'));
        let activeIndex = 0;
        let scrollTicking = false;

        const clampIndex = (index) => Math.max(0, Math.min(slides.length - 1, index));

        const getScrollIndex = () => {
            const slideWidth = track.clientWidth || 1;
            return clampIndex(Math.round(track.scrollLeft / slideWidth));
        };

        const syncControls = (index) => {
            activeIndex = clampIndex(index);
            controls.forEach((control, controlIndex) => {
                const isActive = controlIndex === activeIndex;
                control.classList.toggle('is-active', isActive);
                control.setAttribute('aria-current', isActive ? 'true' : 'false');
            });
        };

        const scrollToIndex = (index, smooth = true) => {
            const targetIndex = clampIndex(index);
            const targetLeft = targetIndex * (track.clientWidth || 0);
            if (!smooth) {
                track.scrollLeft = targetLeft;
            } else {
                track.scrollTo({ left: targetLeft, behavior: 'smooth' });
            }
            syncControls(targetIndex);
        };

        track.addEventListener('scroll', () => {
            if (scrollTicking) {
                return;
            }
            scrollTicking = true;
            window.requestAnimationFrame(() => {
                syncControls(getScrollIndex());
                scrollTicking = false;
            });
        }, { passive: true });

        controls.forEach((control, index) => {
            control.addEventListener('click', () => {
                scrollToIndex(index);
            });
        });

        window.addEventListener('resize', debounce(() => {
            scrollToIndex(activeIndex, false);
        }, 120));

        syncControls(getScrollIndex());
    });
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
    notification.style.cssText = 'top: 16px; left: 50%; transform: translateX(-50%); z-index: 9999; width: min(500px, calc(100vw - 24px)); text-align: center; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.15);';
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

// Scroll to top button
(function() {
    if (document.querySelector('.sf-scroll-top')) {
        return;
    }

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
    const confirmed = window.confirm(message);
    if (confirmed) {
        if (typeof onConfirm === 'function') {
            onConfirm();
        }
        return;
    }
    if (typeof onCancel === 'function') {
        onCancel();
    }
}

// Export functions for use in other scripts
window.getCookie = getCookie;
window.getCsrfToken = getCsrfToken;
window.showNotification = showNotification;
window.showConfirmToast = showConfirmToast;
window.updateCartCounter = updateCartCounter;
window.formatPrice = formatPrice;
window.debounce = debounce;
