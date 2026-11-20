// Bloco: alterna abas do perfil e atualiza seus estados acessíveis.
function alternarAba(abaId, elementoBotao) {
    document.querySelectorAll(".aba-conteudo").forEach((conteudo) => {
        conteudo.classList.toggle("hidden", conteudo.id !== "conteudo-" + abaId);
    });

    document.querySelectorAll(".btn-aba").forEach((botao) => {
        const ativo = botao === elementoBotao;
        botao.setAttribute("aria-selected", ativo ? "true" : "false");
        botao.setAttribute("tabindex", ativo ? "0" : "-1");
        botao.classList.toggle("ui-action", ativo);
        botao.classList.toggle("ui-button-copy", ativo);
        botao.classList.toggle("ui-hover-component", !ativo);
        botao.classList.toggle("ui-text-copy", !ativo);
        botao.classList.toggle("ui-hover-heading", !ativo);
    });
}
