// Bloco: abre e fecha o formulário de criação rápida de fichas.
function abrirModalNomeFicha() {
    document.getElementById("modal_nome_ficha").classList.remove("hidden");
    document.getElementById("nome_personagem").focus();
}

function fecharModalNomeFicha() {
    document.getElementById("modal_nome_ficha").classList.add("hidden");
    document.getElementById("nome_personagem").value = "";
}
