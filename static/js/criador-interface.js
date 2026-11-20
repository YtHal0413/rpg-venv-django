// Bloco: limpeza da ficha e controles dos pain?is laterais.

function limparFichaCompleta() {
    if (!confirm("Tem certeza que deseja limpar todos os dados da ficha? Esta ação não pode ser desfeita.")) return;

    estadoFicha.colunas = {
        1: { ativa: true, abas: [], abaAtivaId: null },
        2: { ativa: true, abas: [], abaAtivaId: null },
        3: { ativa: true, abas: [], abaAtivaId: null }
    };
    renderizarFichaCompleta();
    fecharGavetaLateral("config");
    mostrarToastNotificacao("Limpeza", "Todos os dados foram removidos.", "alerta");
    agendarSalvamento();
}

function abrirGavetaLateral(tipo) {
    fecharGavetaLateral("config");
    fecharGavetaLateral("historico");
    const gaveta = document.getElementById(`gaveta_${tipo}`);
    if (gaveta) {
        gaveta.classList.remove("-translate-x-full");
        if (tipo === "config") renderizarConfiguradorEstrutura();
    }
}

function fecharGavetaLateral(tipo) {
    const gaveta = document.getElementById(`gaveta_${tipo}`);
    if (gaveta) gaveta.classList.add("-translate-x-full");
}

function definirVisibilidade(novaVisibilidade) {
    if (!estadoFicha.podeEditar) {
        mostrarToastNotificacao("Acesso negado", "Você só pode visualizar esta ficha em modo jogo.", "erro");
        return;
    }
    estadoFicha.visibilidade = novaVisibilidade;
    renderizarConfiguradorEstrutura();
    agendarSalvamento();
}
