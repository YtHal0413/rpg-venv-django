// Bloco: controla a abertura do modal de criação de campanhas.
const modalCriarCampanha = document.getElementById("modal_criar_campanha");

function abrirModalCriarCampanha() {
    if (!modalCriarCampanha) return;

    modalCriarCampanha.classList.remove("hidden");
    modalCriarCampanha.querySelector("#id_titulo")?.focus();
}

function fecharModalCriarCampanha() {
    modalCriarCampanha?.classList.add("hidden");
}

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") fecharModalCriarCampanha();
});

if (document.getElementById("gerenciar-campanha-page")?.dataset.openModal === "true") {
    abrirModalCriarCampanha();
}
