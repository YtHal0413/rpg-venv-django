// Bloco: persist?ncia e manipula??o de abas, se??es e componentes.

async function enviarRequisicaoFicha(url, options = {}) {
    const { headers = {}, ...opcoesFetch } = options;
    const metodo = (opcoesFetch.method || "GET").toUpperCase();
    const cabecalhos = { ...headers };
    if (metodo !== "GET" && metodo !== "HEAD") {
        cabecalhos["X-CSRFToken"] = obterTokenCsrf();
    }
    if (opcoesFetch.body && !(opcoesFetch.body instanceof FormData)) {
        cabecalhos["Content-Type"] = cabecalhos["Content-Type"] || "application/json";
    }
    try {
        const resposta = await fetch(url, { ...opcoesFetch, headers: cabecalhos });
        const dados = await resposta.json().catch(() => null);
        if (!resposta.ok) {
            const mensagem = dados?.erro || resposta.statusText || "Erro ao processar a requisição.";
            throw new Error(mensagem);
        }
        return dados;
    } catch (erro) {
        console.warn("Erro na API de ficha:", erro);
        throw erro;
    }
}

function alternarAbaColuna(numColuna, abaId) {
    estadoFicha.colunas[numColuna].abaAtivaId = abaId;
    renderizarColuna(numColuna);
    renderizarConfiguradorEstrutura();
}

async function novaAba(colunaNum) {
    if (!estadoFicha.podeEditar) {
        mostrarToastNotificacao("Acesso negado", "Você só pode visualizar esta ficha em modo jogo.", "erro");
        return;
    }
    const col = estadoFicha.colunas[colunaNum];
    if (col.abas.length >= 3) {
        mostrarToastNotificacao("Limite Excedido", "Máximo de 3 abas por coluna.", "erro");
        return;
    }
    const titulo = prompt("Título da nova aba:");
    if (!titulo || titulo.trim() === "") return;

    let abaId;
    try {
        const dados = await enviarRequisicaoFicha(`/api/ficha/${estadoFicha.id}/aba`, {
            method: "POST",
            body: JSON.stringify({ titulo: titulo.trim(), posicaoColuna: colunaNum })
        });
        abaId = dados?.aba?.id;
    } catch (erro) {
        mostrarToastNotificacao("Aviso", "Não foi possível sincronizar a nova aba com o servidor. A aba será criada localmente e salva em seguida.", "aviso");
    }

    const novaAba = { id: abaId || ++idGeradorInterno, titulo: titulo.trim(), secoes: [] };
    col.abas.push(novaAba);
    col.abaAtivaId = novaAba.id;
    renderizarFichaCompleta();
    mostrarToastNotificacao("Sucesso", `Aba "${titulo}" adicionada!`, "sucesso");
    agendarSalvamento();
    renderizarConfiguradorEstrutura();
}

async function removerAbaColuna(colunaNum, abaId) {
    if (!estadoFicha.podeEditar) {
        mostrarToastNotificacao("Acesso negado", "Você só pode visualizar esta ficha em modo jogo.", "erro");
        return;
    }

    const col = estadoFicha.colunas[colunaNum];
    const abaARemover = col.abas.find(a => a.id === abaId);

    if (abaARemover && (abaARemover.ehPadrao === true || abaARemover.titulo === "Geral")) {
        mostrarToastNotificacao("Ação não permitida", "A aba 'Geral' não pode ser removida.", "aviso");
        return;
    }

    try {
        await enviarRequisicaoFicha(`/api/ficha/${estadoFicha.id}/aba/${abaId}`, { method: "DELETE" });
    } catch (erro) {
        mostrarToastNotificacao("Aviso", "Não foi possível remover a aba no servidor. A aba será removida localmente.", "aviso");
    }

    col.abas = col.abas.filter(a => a.id !== abaId);
    if (col.abaAtivaId === abaId) {
        col.abaAtivaId = col.abas.length > 0 ? col.abas[0].id : null;
    }
    renderizarFichaCompleta();
    agendarSalvamento();
    renderizarConfiguradorEstrutura();
}

function abrirModalNovaSecao(colunaNum) {
    colunaAlvoNovaSecao = colunaNum;
    document.getElementById("modal_nova_secao").classList.remove("hidden");
}

function fecharModalNovaSecao() {
    document.getElementById("modal_nova_secao").classList.add("hidden");
    document.getElementById("titulo_secao_novo").value = "";
}

async function salvarNovaSecao() {
    if (!estadoFicha.podeEditar) {
        mostrarToastNotificacao("Acesso negado", "Você só pode visualizar esta ficha em modo jogo.", "erro");
        return;
    }
    const titulo = document.getElementById("titulo_secao_novo").value.trim();
    const tipo = document.getElementById("tipo_componente_secao").value;
    if (!titulo) {
        mostrarToastNotificacao("Erro", "Título da seção é obrigatório.", "erro");
        return;
    }

    const col = estadoFicha.colunas[colunaAlvoNovaSecao];
    const aba = col.abas.find(a => a.id === col.abaAtivaId);
    if (!aba) {
        mostrarToastNotificacao("Erro", "Nenhuma aba ativa.", "erro");
        return;
    }

    let secaoId;
    try {
        const dados = await enviarRequisicaoFicha(`/api/ficha/${estadoFicha.id}/secao`, {
            method: "POST",
            body: JSON.stringify({ titulo, abaId: aba.id, tipo })
        });
        secaoId = dados?.secao?.id;
    } catch (erro) {
        mostrarToastNotificacao("Aviso", "Não foi possível sincronizar a seção com o servidor. A seção será criada localmente e salva em seguida.", "aviso");
    }

    aba.secoes.push({ id: secaoId || ++idGeradorInterno, titulo, tipo, componentes: [] });
    fecharModalNovaSecao();
    renderizarFichaCompleta();
    mostrarToastNotificacao("Sucesso", `Seção "${titulo}" criada!`, "sucesso");
    agendarSalvamento();
}

async function removerSecaoAba(numColuna, secaoId) {
    if (!estadoFicha.podeEditar) {
        mostrarToastNotificacao("Acesso negado", "Você só pode visualizar esta ficha em modo jogo.", "erro");
        return;
    }
    const col = estadoFicha.colunas[numColuna];
    const aba = col.abas.find(a => a.id === col.abaAtivaId);

    try {
        await enviarRequisicaoFicha(`/api/ficha/${estadoFicha.id}/secao/${secaoId}`, { method: "DELETE" });
    } catch (erro) {
        mostrarToastNotificacao("Aviso", "Não foi possível remover a seção no servidor. A seção será removida localmente.", "aviso");
    }

    if (aba) {
        aba.secoes = aba.secoes.filter(s => s.id !== secaoId);
        renderizarFichaCompleta();
        agendarSalvamento();
    }
}

async function adicionarComponenteSecao(numColuna, secaoId, tipo) {
    if (!estadoFicha.podeEditar) {
        mostrarToastNotificacao("Acesso negado", "Você só pode visualizar esta ficha em modo jogo.", "erro");
        return;
    }
    const col = estadoFicha.colunas[numColuna];
    const aba = col.abas.find(a => a.id === col.abaAtivaId);
    if (!aba) return;
    const secao = aba.secoes.find(s => s.id === secaoId);
    if (!secao) return;
    secao.componentes = secao.componentes || [];

    let novoComp = null;
    try {
        const dados = await enviarRequisicaoFicha(`/api/ficha/${estadoFicha.id}/componente`, {
            method: "POST",
            body: JSON.stringify({ secaoId, tipo })
        });
        novoComp = dados?.componente;
    } catch (erro) {
        mostrarToastNotificacao("Aviso", "Não foi possível sincronizar o componente com o servidor. O componente será criado localmente e salvo em seguida.", "aviso");
    }

    if (!novoComp) {
        novoComp = { id: ++idGeradorInterno };
        switch(tipo) {
            case "AtributoSimples": novoComp.nomeAtributo = ""; novoComp.valorAtributo = 0; break;
            case "AtributoDuplo": novoComp.nomeAtributo = ""; novoComp.valorGrande = 0; novoComp.valorPequeno = 0; break;
            case "AtributoComplexo": novoComp.nomeAtributo = ""; novoComp.valorBase = 0; novoComp.valorBonus = 0; novoComp.valorOutros = 0; novoComp.subtituloAnotacao = ""; break;
            case "Contador": novoComp.rotulo = ""; novoComp.valorAtual = 0; novoComp.valorMaximo = 10; novoComp.corSeletor = "#4A4E69"; break;
            case "Checkbox": novoComp.rotulo = ""; novoComp.estaMarcado = false; break;
            case "InformacaoCurta": novoComp.rotulo = ""; novoComp.campoTexto = ""; break;
            case "AnotacaoSimples": novoComp.rotulo = ""; novoComp.descricao = ""; break;
            case "AnotacaoCheckbox": novoComp.rotulo = ""; novoComp.descricao = ""; novoComp.estaMarcado = false; break;
            case "AnotacaoDetalhada": novoComp.rotulo = ""; novoComp.descricao = ""; novoComp.anotacaoExtra = ""; break;
            default: break;
        }
    }

    secao.componentes.push(novoComp);
    renderizarFichaCompleta();
    mostrarToastNotificacao("Sucesso", "Elemento adicionado.", "sucesso");
    agendarSalvamento();
}

async function removerComponenteFicha(numColuna, secaoId, compId) {
    if (!estadoFicha.podeEditar) {
        mostrarToastNotificacao("Acesso negado", "Você só pode visualizar esta ficha em modo jogo.", "erro");
        return;
    }
    const col = estadoFicha.colunas[numColuna];
    const aba = col.abas.find(a => a.id === col.abaAtivaId);
    if (!aba) return;
    const secao = aba.secoes.find(s => s.id === secaoId);
    if (!secao) return;

    try {
        await enviarRequisicaoFicha(`/api/ficha/${estadoFicha.id}/componente/${compId}`, { method: "DELETE" });
    } catch (erro) {
        mostrarToastNotificacao("Aviso", "Não foi possível remover o componente no servidor. A remoção será aplicada localmente.", "aviso");
    }

    secao.componentes = secao.componentes.filter(c => c.id !== compId);
    renderizarFichaCompleta();
    agendarSalvamento();
}

function atualizarValorComponente(numColuna, secaoId, compId, campo, valor) {
    const col = estadoFicha.colunas[numColuna];
    const aba = col.abas.find(a => a.id === col.abaAtivaId);
    if (!aba) return;
    const secao = aba.secoes.find(s => s.id === secaoId);
    if (!secao) return;
    const comp = secao.componentes.find(c => c.id === compId);
    if (!comp) return;

    comp[campo] = valor;
    agendarSalvamento();
}

function recalcularTotalComplexo(numColuna, secaoId, compId) {
    const col = estadoFicha.colunas[numColuna];
    const aba = col.abas.find(a => a.id === col.abaAtivaId);
    if (!aba) return;
    const secao = aba.secoes.find(s => s.id === secaoId);
    if (!secao) return;
    const comp = secao.componentes.find(c => c.id === compId);
    if (comp) {
        const display = document.getElementById(`total_complexo_${compId}`);
        if (display) {
            display.textContent = (Number(comp.valorBase) || 0) + (Number(comp.valorBonus) || 0) + (Number(comp.valorOutros) || 0);
        }
    }
}

function definirModo(novoModo) {
    if (!estadoFicha.podeEditar) {
        estadoFicha.modo = "Jogo";
        const btnJogo = document.getElementById("btn_modo_jogo");
        if (btnJogo) btnJogo.className = "px-4 py-2 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 ui-action ui-button-copy shadow-lg ui-shadow";
        document.querySelectorAll(".btn-edicao-visivel").forEach(el => el.classList.add("hidden"));
        renderizarFichaCompleta();
        return;
    }
    estadoFicha.modo = novoModo;
    const btnJogo = document.getElementById("btn_modo_jogo");
    const btnEdicao = document.getElementById("btn_modo_edicao");

    if (novoModo === "Jogo") {
        btnJogo.className = "px-4 py-2 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 ui-action ui-button-copy shadow-lg ui-shadow";
        btnEdicao.className = "px-4 py-2 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 ui-text-muted ui-hover-heading";
        document.querySelectorAll(".btn-edicao-visivel").forEach(el => el.classList.add("hidden"));
    } else {
        btnEdicao.className = "px-4 py-2 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 ui-action ui-button-copy shadow-lg ui-shadow";
        btnJogo.className = "px-4 py-2 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 ui-text-muted ui-hover-heading";
        document.querySelectorAll(".btn-edicao-visivel").forEach(el => el.classList.remove("hidden"));
    }
    renderizarFichaCompleta();
    agendarSalvamento();
}
