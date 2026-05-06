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

// Mobile footer accordion
(function() {
    const root = document.querySelector('[data-footer-accordion]');
    if (!root || typeof window.matchMedia !== 'function') {
        return;
    }

    const mediaQuery = window.matchMedia('(max-width: 767.98px)');
    const sections = Array.from(root.querySelectorAll('[data-footer-accordion-section]'))
        .map((section) => {
            const button = section.querySelector('[data-footer-accordion-trigger]');
            const panel = section.querySelector('[data-footer-accordion-panel]');

            if (!button || !panel) {
                return null;
            }

            return { button, panel };
        })
        .filter(Boolean);

    if (!sections.length) {
        return;
    }

    function setSectionState(section, expanded, persist) {
        section.button.setAttribute('aria-expanded', String(expanded));
        section.panel.hidden = !expanded;

        if (persist) {
            section.button.dataset.footerExpanded = String(expanded);
        }
    }

    function getStoredState(section) {
        if (!section.button.dataset.footerExpanded) {
            const defaultOpen = section.button.getAttribute('data-footer-default-open') === 'true';
            section.button.dataset.footerExpanded = String(defaultOpen);
        }

        return section.button.dataset.footerExpanded === 'true';
    }

    function syncFooterAccordion() {
        if (mediaQuery.matches) {
            root.classList.add('is-ready');
            sections.forEach((section) => {
                setSectionState(section, getStoredState(section), false);
            });
            return;
        }

        root.classList.remove('is-ready');
        sections.forEach((section) => {
            setSectionState(section, true, false);
        });
    }

    sections.forEach((section) => {
        section.button.addEventListener('click', () => {
            if (!mediaQuery.matches) {
                return;
            }

            const expanded = section.button.getAttribute('aria-expanded') === 'true';
            setSectionState(section, !expanded, true);
        });
    });

    syncFooterAccordion();

    if (typeof mediaQuery.addEventListener === 'function') {
        mediaQuery.addEventListener('change', syncFooterAccordion);
    } else if (typeof mediaQuery.addListener === 'function') {
        mediaQuery.addListener(syncFooterAccordion);
    }
})();

// Product card sliders (catalog cards only)
(function() {
    const cardSwipers = document.querySelectorAll('[data-sf-product-swiper]');
    if (!cardSwipers.length || typeof window.Swiper !== 'function') {
        return;
    }

    cardSwipers.forEach((swiperEl) => {
        const paginationEl = swiperEl.querySelector('.sf-product-card-swiper-pagination');
        const nextEl = swiperEl.querySelector('.sf-product-card-swiper-next');
        const prevEl = swiperEl.querySelector('.sf-product-card-swiper-prev');

        const options = {
            slidesPerView: 1,
            spaceBetween: 0,
            speed: 340,
            watchOverflow: true,
            threshold: 6,
            resistanceRatio: 0.85,
            grabCursor: true,
            touchStartPreventDefault: false,
            preventClicksPropagation: true,
        };

        if (paginationEl) {
            options.pagination = {
                el: paginationEl,
                clickable: true,
            };
        }

        if (nextEl && prevEl) {
            options.navigation = {
                nextEl,
                prevEl,
            };
            [nextEl, prevEl].forEach((navButton) => {
                navButton.addEventListener('click', (event) => event.stopPropagation());
            });
        }

        new window.Swiper(swiperEl, options);
    });
})();

// Product page gallery (Swiper + Fancybox)
(function() {
    const galleryRoots = document.querySelectorAll('[data-sf-product-detail-gallery]');
    if (!galleryRoots.length || typeof window.Swiper !== 'function') {
        return;
    }

    galleryRoots.forEach((root) => {
        const mainEl = root.querySelector('[data-sf-product-detail-main]');
        if (!mainEl) {
            return;
        }

        const galleryCount = Number(root.getAttribute('data-sf-gallery-count') || '0');
        const hasMultipleSlides = galleryCount > 1;
        const paginationEl = root.querySelector('.sf-product-gallery-pagination');
        const nextEl = root.querySelector('.sf-product-gallery-next');
        const prevEl = root.querySelector('.sf-product-gallery-prev');
        const thumbsEl = root.querySelector('[data-sf-product-detail-thumbs]');
        let thumbsSwiper = null;

        if (hasMultipleSlides && thumbsEl) {
            thumbsSwiper = new window.Swiper(thumbsEl, {
                slidesPerView: 'auto',
                spaceBetween: 12,
                watchSlidesProgress: true,
                watchOverflow: true,
                freeMode: true,
                slideToClickedSlide: true,
                breakpoints: {
                    768: {
                        spaceBetween: 16,
                    },
                },
            });
        }

        const options = {
            slidesPerView: 1,
            spaceBetween: 0,
            speed: 360,
            watchOverflow: true,
            threshold: 6,
            keyboard: {
                enabled: true,
                onlyInViewport: true,
            },
        };

        if (hasMultipleSlides && paginationEl) {
            options.pagination = {
                el: paginationEl,
                clickable: true,
            };
        }

        if (hasMultipleSlides && nextEl && prevEl) {
            options.navigation = {
                nextEl,
                prevEl,
            };
        }

        if (hasMultipleSlides && thumbsSwiper) {
            options.thumbs = {
                swiper: thumbsSwiper,
            };
        }

        const mainSwiper = new window.Swiper(mainEl, options);

        if (hasMultipleSlides && thumbsEl) {
            const thumbButtons = Array.from(thumbsEl.querySelectorAll('.sf-product-thumb'));
            const syncThumbState = (activeIndex) => {
                thumbButtons.forEach((thumbButton, index) => {
                    thumbButton.setAttribute('aria-current', index === activeIndex ? 'true' : 'false');
                });
            };

            syncThumbState(mainSwiper.activeIndex || 0);
            mainSwiper.on('slideChange', () => {
                syncThumbState(mainSwiper.activeIndex || 0);
            });
        }
    });

    if (window.Fancybox && typeof window.Fancybox.bind === 'function') {
        window.Fancybox.bind('[data-fancybox^="product-gallery-"]');
    }
})();

// Avatar upload validation
(function() {
    const avatarInputs = document.querySelectorAll('input[data-avatar-upload="true"]');
    if (!avatarInputs.length) {
        return;
    }

    const allowedExtensions = ['jpg', 'jpeg', 'png', 'webp'];

    function removeClientError(input) {
        const group = input.closest('.sf-form-group') || input.parentElement;
        const error = group?.querySelector('[data-avatar-client-error="true"]');
        if (error) {
            error.remove();
        }
    }

    function showClientError(input, message) {
        const group = input.closest('.sf-form-group') || input.parentElement;
        if (!group) {
            return;
        }

        removeClientError(input);

        const wrapper = document.createElement('div');
        wrapper.className = 'sf-field-errors';
        wrapper.setAttribute('data-avatar-client-error', 'true');

        const error = document.createElement('div');
        error.textContent = message;
        wrapper.appendChild(error);
        group.appendChild(wrapper);
    }

    avatarInputs.forEach((input) => {
        input.addEventListener('change', () => {
            const file = input.files && input.files[0];
            removeClientError(input);

            if (!file) {
                return;
            }

            const maxSize = Number(input.getAttribute('data-max-size') || '0');
            if (maxSize && file.size > maxSize) {
                showClientError(input, input.getAttribute('data-size-error') || 'Файл слишком большой.');
                input.value = '';
                return;
            }

            const extension = file.name.split('.').pop().toLowerCase();
            const acceptedTypes = (input.getAttribute('accept') || '')
                .split(',')
                .map((type) => type.trim())
                .filter(Boolean);
            const typeAllowed = !file.type || acceptedTypes.includes(file.type);

            if (!allowedExtensions.includes(extension) || !typeAllowed) {
                showClientError(input, input.getAttribute('data-type-error') || 'Недопустимый формат файла.');
                input.value = '';
            }
        });
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
