// Bloco: mantém o estado da ficha e inicia a sincronização com o servidor.

let estadoFicha = {
    id: typeof fichaID !== 'undefined' ? fichaID : 1,
    nome: "Novo Personagem",
    subtitulo: "",
    modo: typeof modoInicial !== 'undefined' ? modoInicial : "Jogo",
    podeEditar: typeof podeEditar !== 'undefined' ? !!podeEditar : true,
    avatar: null,
    visibilidade: typeof visibilidadeInicial !== 'undefined' ? visibilidadeInicial : "todos",
    colunas: {
        1: { ativa: true, abas: [], abaAtivaId: null },
        2: { ativa: true, abas: [], abaAtivaId: null },
        3: { ativa: true, abas: [], abaAtivaId: null }
    }
};

let pilhaDadosAtiva = {};
let historicoRolagensSessao = [];
let idGeradorInterno = 1000;
let temporizadorSalvar = null;
let salvamentoEmAndamento = false;
let salvamentoPendente = false;
let revisaoEstadoFicha = 0;
let colunaAlvoNovaSecao = 1;

// Bloco: conecta os campos da ficha aos eventos de edição.
window.addEventListener("DOMContentLoaded", () => {
    inicializarEventosFicha();
    carregarFichaDoServidor();
});
window.addEventListener("pageshow", () => {
    renderizarFichaCompleta();
});

function inicializarEventosFicha() {
    const inputNome = document.getElementById("nome_personagem_topo");
    if (inputNome) {
        inputNome.addEventListener("input", (e) => {
            estadoFicha.nome = e.target.value;
            const cardNome = document.getElementById("nome_personagem_card");
            if (cardNome) cardNome.textContent = e.target.value;
            agendarSalvamento();
        });
    }

    const inputSubtitulo = document.getElementById("subtitulo_card");
    if (inputSubtitulo) {
        inputSubtitulo.addEventListener("input", (e) => {
            estadoFicha.subtitulo = e.target.value;
            agendarSalvamento();
        });
    }
}

function obterTokenCsrf() {
    return document.querySelector("#csrf-form [name='csrfmiddlewaretoken']")?.value || "";
}

function atualizarStatusSincronizacao(texto, estado = "") {
    const indicador = document.getElementById("status_sincronizacao");
    if (!indicador) return;
    indicador.textContent = texto;
    indicador.dataset.estado = estado;
    indicador.classList.toggle("ui-text-danger", estado === "erro");
    indicador.classList.toggle("ui-text-positive", estado === "sucesso");
}

// Bloco: carrega e persiste os dados da ficha pela API.
async function carregarFichaDoServidor() {
    atualizarStatusSincronizacao("Carregando ficha…");
    try {
        const campanhaId = new URLSearchParams(window.location.search).get("campanha");
        const parametros = campanhaId ? `?campanha=${encodeURIComponent(campanhaId)}` : "";
        const resposta = await fetch(`/api/ficha/${estadoFicha.id}${parametros}`);
        if (!resposta.ok) {
            throw new Error(`Não foi possível carregar a ficha (HTTP ${resposta.status}).`);
        }
        if (resposta.ok) {
            const dados = await resposta.json();
            if (dados && dados.id) {
                estadoFicha = {
                    ...estadoFicha,
                    ...dados,
                    modo: "Jogo",
                    visibilidade: dados.visibilidade === "mestres" ? "mestres" : "todos",
                    podeEditar: estadoFicha.podeEditar,
                };

                normalizarIdsFicha();
                garantirAbaGeralPrimeiraColuna();
                garantirAbasAtivas();
                renderizarFichaCompleta();

                if (dados.avatar) {
                    const img = document.getElementById('avatar_imagem');
                    const placeholder = document.getElementById('avatar_placeholder');
                    if (img) {
                        img.src = dados.avatar;
                        img.classList.remove('hidden');
                        if (placeholder) placeholder.classList.add('hidden');
                    }
                } else {
                    const img = document.getElementById('avatar_imagem');
                    const placeholder = document.getElementById('avatar_placeholder');
                    if (img) img.classList.add('hidden');
                    if (placeholder) placeholder.classList.remove('hidden');
                }
                atualizarStatusSincronizacao("Ficha sincronizada", "sucesso");
                return;
            }
        }
        throw new Error("O servidor retornou uma ficha inválida.");
    } catch (erro) {
        console.warn("Falha ao carregar ficha:", erro);
        renderizarFichaCompleta();
        atualizarStatusSincronizacao("Falha ao carregar ficha", "erro");
        mostrarToastNotificacao("Erro de sincronização", erro.message, "erro");
    }
}

function garantirAbaGeralPrimeiraColuna() {
    if (!estadoFicha.colunas[1]) return;

    const col1 = estadoFicha.colunas[1];
    const temAbaGeral = col1.abas && col1.abas.some(a => a.ehPadrao === true || a.titulo === "Geral");

    if (!temAbaGeral) {
        const abaGeral = {
            id: 1000,
            titulo: "Geral",
            ehPadrao: true,
            secoes: []
        };
        col1.abas = col1.abas || [];
        col1.abas.unshift(abaGeral);
        col1.abaAtivaId = 1000;
    }
}

function garantirAbasAtivas() {
    Object.values(estadoFicha.colunas).forEach(coluna => {
        if (coluna && coluna.abas && coluna.abas.length > 0) {
            const temAtiva = coluna.abaAtivaId != null && coluna.abas.some(aba => aba.id == coluna.abaAtivaId);
            if (!temAtiva) {
                coluna.abaAtivaId = coluna.abas[0].id;
            }
        }
    });
}

function normalizarIdsFicha() {
    let maiorId = idGeradorInterno;
    Object.values(estadoFicha.colunas).forEach(coluna => {
        if (!coluna || !coluna.abas) return;
        coluna.abas.forEach(aba => {
            if (!aba.id || aba.id === 0) {
                aba.id = ++maiorId;
            } else {
                maiorId = Math.max(maiorId, aba.id);
            }
            if (aba.secoes) {
                aba.secoes.forEach(secao => {
                    if (!secao.id || secao.id === 0) {
                        secao.id = ++maiorId;
                    } else {
                        maiorId = Math.max(maiorId, secao.id);
                    }
                    if (secao.componentes) {
                        secao.componentes.forEach(comp => {
                            if (!comp.id || comp.id === 0) {
                                comp.id = ++maiorId;
                            } else {
                                maiorId = Math.max(maiorId, comp.id);
                            }
                        });
                    }
                });
            }
        });
        if (coluna.abaAtivaId == null || !coluna.abas.some(aba => aba.id == coluna.abaAtivaId)) {
            coluna.abaAtivaId = coluna.abas.length > 0 ? coluna.abas[0].id : null;
        }
    });
    idGeradorInterno = maiorId;
}

function agendarSalvamento() {
    if (!estadoFicha.podeEditar) return;
    revisaoEstadoFicha += 1;
    atualizarStatusSincronizacao("Alterações pendentes");
    if (temporizadorSalvar) clearTimeout(temporizadorSalvar);
    temporizadorSalvar = setTimeout(() => {
        temporizadorSalvar = null;
        salvarFichaNoServidor();
    }, 600);
}

async function salvarFichaNoServidor() {
    if (salvamentoEmAndamento) {
        salvamentoPendente = true;
        return false;
    }

    salvamentoEmAndamento = true;
    let salvou = false;
    try {
        do {
            salvamentoPendente = false;
            if (temporizadorSalvar) {
                clearTimeout(temporizadorSalvar);
                temporizadorSalvar = null;
            }
            const revisaoEnviada = revisaoEstadoFicha;
            atualizarStatusSincronizacao("Sincronizando…");
            const resposta = await fetch(`/api/ficha/${estadoFicha.id}`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": obterTokenCsrf(),
                },
                body: JSON.stringify(estadoFicha)
            });
            const dados = await resposta.json().catch(() => null);
            if (!resposta.ok) {
                throw new Error(dados?.erro || `Falha ao salvar a ficha (HTTP ${resposta.status}).`);
            }
            salvou = true;
            if (revisaoEnviada !== revisaoEstadoFicha) {
                salvamentoPendente = true;
            }
        } while (salvamentoPendente);
        atualizarStatusSincronizacao("Todas as alterações salvas", "sucesso");
    } catch (erro) {
        console.warn("Falha ao salvar:", erro);
        atualizarStatusSincronizacao("Falha ao sincronizar", "erro");
        mostrarToastNotificacao("Falha ao salvar ficha", erro.message, "erro");
    } finally {
        salvamentoEmAndamento = false;
        if (salvamentoPendente && salvou) {
            salvamentoPendente = false;
            salvarFichaNoServidor();
        }
    }
    return salvou;
}
