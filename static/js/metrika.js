(function(window, document) {
    'use strict';

    if (window.__matchdayMetrikaScriptLoaded) {
        return;
    }
    window.__matchdayMetrikaScriptLoaded = true;

    function readJsonScript(id) {
        const element = document.getElementById(id);
        if (!element) {
            return null;
        }

        try {
            return JSON.parse(element.textContent || '{}');
        } catch (error) {
            return null;
        }
    }

    const config = readJsonScript('matchday-metrika-config');
    if (!config || !config.enabled || !/^\d+$/.test(String(config.counterId || ''))) {
        return;
    }

    const counterId = Number(config.counterId);
    const initialEvents = readJsonScript('matchday-metrika-events') || [];

    function hasConsent() {
        if (!config.requireConsent) {
            return true;
        }

        if (window.matchdayMetrikaConsentGranted === true) {
            return true;
        }

        try {
            return window.localStorage.getItem('cookie_consent') === 'accepted';
        } catch (error) {
            return false;
        }
    }

    function pushEcommerceEvent(event) {
        if (!event || typeof event !== 'object') {
            return;
        }
        window.dataLayer = window.dataLayer || [];
        window.dataLayer.push(event);
    }

    function initMetrika() {
        if (window.__matchdayMetrikaInitialized || !hasConsent()) {
            return;
        }
        window.__matchdayMetrikaInitialized = true;

        window.dataLayer = window.dataLayer || [];

        (function(m, e, t, r, i, k, a) {
            m[i] = m[i] || function() {
                (m[i].a = m[i].a || []).push(arguments);
            };
            m[i].l = 1 * new Date();
            k = e.createElement(t);
            a = e.getElementsByTagName(t)[0];
            k.async = 1;
            k.src = r;
            a.parentNode.insertBefore(k, a);
        })(window, document, 'script', 'https://mc.yandex.ru/metrika/tag.js', 'ym');

        window.ym(counterId, 'init', config.options || {});

        if (Array.isArray(initialEvents)) {
            initialEvents.forEach(pushEcommerceEvent);
        }
    }

    window.matchdayMetrika = window.matchdayMetrika || {};
    window.matchdayMetrika.init = initMetrika;
    window.matchdayMetrika.pushEcommerce = pushEcommerceEvent;

    window.addEventListener('matchday:cookie-consent-changed', function(event) {
        if (event.detail && event.detail.value === 'accepted') {
            initMetrika();
        }
    });

    window.addEventListener('storage', function(event) {
        if (event.key === 'cookie_consent' && event.newValue === 'accepted') {
            initMetrika();
        }
    });

    initMetrika();
})(window, document);
