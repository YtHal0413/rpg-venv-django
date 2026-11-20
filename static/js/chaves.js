// Bloco: controla compra, resgate e atualização das chaves de acesso.
(() => {
    const modal = document.getElementById("modal_chaves");
    const openButton = document.getElementById("abrir_modal_chaves");
    if (!modal || !openButton) return;

    const closeButton = modal.querySelector("[data-fechar-modal]");
    let previouslyFocusedElement = null;

    function openModal() {
        previouslyFocusedElement = document.activeElement;
        modal.classList.remove("hidden");
        modal.setAttribute("aria-hidden", "false");
        closeButton.focus();
    }

    function closeModal() {
        modal.classList.add("hidden");
        modal.setAttribute("aria-hidden", "true");
        if (previouslyFocusedElement) previouslyFocusedElement.focus();
    }

    function getFocusableElements() {
        return Array.from(modal.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )).filter(element => element.getClientRects().length > 0);
    }

    openButton.addEventListener("click", openModal);
    closeButton.addEventListener("click", closeModal);
    modal.addEventListener("click", event => {
        if (event.target === modal) closeModal();
    });
    document.addEventListener("keydown", event => {
        if (modal.classList.contains("hidden")) return;

        if (event.key === "Escape") {
            closeModal();
            return;
        }

        if (event.key !== "Tab") return;

        const focusableElements = getFocusableElements();
        if (focusableElements.length === 0) {
            event.preventDefault();
            closeButton.focus();
            return;
        }

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];
        if (event.shiftKey && (
        document.activeElement === firstElement || !modal.contains(document.activeElement)
        )) {
            event.preventDefault();
            lastElement.focus();
        } else if (!event.shiftKey && (
        document.activeElement === lastElement || !modal.contains(document.activeElement)
        )) {
            event.preventDefault();
            firstElement.focus();
        }
    });
    modal.querySelectorAll("[data-confirmar-compra]").forEach(form => {
        form.addEventListener("submit", event => {
            if (!window.confirm(
            "Confirmar compra? (Apenas demonstrativa, nenhuma cobrança será realizada)."
            )) {
                event.preventDefault();
            }
        });
    });

    if (modal.getAttribute("aria-hidden") === "false") {
        modal.querySelector("[data-fechar-modal]").focus();
    }
})();
