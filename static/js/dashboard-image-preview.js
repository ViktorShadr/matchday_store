/**
 * Product image preview for dashboard image upload form.
 * Compatible with strict CSP because it is loaded as an external static asset.
 */
(function() {
    const ROOT_SELECTOR = '[data-image-preview-root]';
    const INITIALIZED_DATA_ATTR = 'imagePreviewInitialized';

    function initImagePreview(root) {
        if (!root || root.dataset[INITIALIZED_DATA_ATTR] === 'true') {
            return;
        }

        const imageInput = root.querySelector('input[type="file"]');
        const previewContainer = root.querySelector('[data-image-preview-container]');
        const previewImage = root.querySelector('[data-image-preview-image]');
        const previewName = root.querySelector('[data-image-preview-name]');
        const replaceImageButton = root.querySelector('[data-image-preview-replace]');
        const clearImageButton = root.querySelector('[data-image-preview-clear]');

        if (!imageInput || !previewContainer || !previewImage || !previewName) {
            return;
        }

        let objectUrl = null;

        function releaseObjectUrl() {
            if (!objectUrl) {
                return;
            }
            URL.revokeObjectURL(objectUrl);
            objectUrl = null;
        }

        function resetPreview() {
            releaseObjectUrl();
            previewImage.removeAttribute('src');
            previewName.textContent = '';
            previewContainer.classList.add('d-none');
        }

        function showPreview(file) {
            if (!file || typeof file.type !== 'string' || !file.type.startsWith('image/')) {
                resetPreview();
                return;
            }

            releaseObjectUrl();
            objectUrl = URL.createObjectURL(file);
            previewImage.src = objectUrl;
            previewName.textContent = file.name || '';
            previewContainer.classList.remove('d-none');
        }

        function onImageChange() {
            const file = imageInput.files && imageInput.files[0];
            showPreview(file);
        }

        imageInput.addEventListener('change', onImageChange);

        if (replaceImageButton) {
            replaceImageButton.addEventListener('click', function() {
                imageInput.click();
            });
        }

        if (clearImageButton) {
            clearImageButton.addEventListener('click', function() {
                imageInput.value = '';
                resetPreview();
            });
        }

        root.addEventListener('reset', function() {
            window.requestAnimationFrame(resetPreview);
        });

        window.addEventListener('pagehide', releaseObjectUrl, { once: true });
        onImageChange();

        root.dataset[INITIALIZED_DATA_ATTR] = 'true';
    }

    document.querySelectorAll(ROOT_SELECTOR).forEach(initImagePreview);
})();
