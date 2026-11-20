/* Bloco: fecha notificações manualmente e remove mensagens expiradas. */
function fecharFlash(button) {
    const flash = button.closest(".flash-message");
    if (!flash) return;

    flash.classList.add("fechando");
    setTimeout(() => flash.remove(), 300);
}

document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".flash-message").forEach((flash) => {
        setTimeout(() => {
            if (!flash.parentNode) return;

            flash.classList.add("fechando");
            setTimeout(() => flash.remove(), 300);
        }, Number(flash.dataset.duration) || 3000);
    });
});
