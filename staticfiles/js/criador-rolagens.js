// Bloco: configura??o, execu??o e hist?rico de rolagens.

function abrirDiceRoller() {
    document.getElementById("modal_dice_roller").classList.remove("hidden");
}

function fecharDiceRoller() {
    document.getElementById("modal_dice_roller").classList.add("hidden");
}

function adicionarDadoPilha(dado) {
    if (!pilhaDadosAtiva[dado]) pilhaDadosAtiva[dado] = 0;
    pilhaDadosAtiva[dado]++;
    const badge = document.getElementById(`badge_${dado}`);
    if (badge) {
        badge.textContent = pilhaDadosAtiva[dado];
        badge.classList.remove("hidden");
    }
    atualizarFormulaExibida();
}

function removerUltimoDadoPilha() {
    const chaves = Object.keys(pilhaDadosAtiva);
    if (chaves.length === 0) return;
    const ultima = chaves[chaves.length - 1];
    if (pilhaDadosAtiva[ultima] > 0) {
        pilhaDadosAtiva[ultima]--;
        const badge = document.getElementById(`badge_${ultima}`);
        if (badge) {
            badge.textContent = pilhaDadosAtiva[ultima];
            if (pilhaDadosAtiva[ultima] === 0) {
                badge.classList.add("hidden");
                delete pilhaDadosAtiva[ultima];
            }
        }
    }
    atualizarFormulaExibida();
}

function limparPilhaDados() {
    pilhaDadosAtiva = {};
    document.querySelectorAll("[id^='badge_']").forEach(b => {
        b.textContent = "0";
        b.classList.add("hidden");
    });
    const bonusInput = document.getElementById("bonus_dados");
    if (bonusInput) bonusInput.value = "0";
    const formulaInput = document.getElementById("input_formula_rolagem");
    if (formulaInput) formulaInput.value = "";
    atualizarFormulaExibida();
}

function atualizarFormulaExibida() {
    const container = document.getElementById("formula_rolagem_exibida");
    if (!container) return;
    const partes = [];
    for (const [dado, qtd] of Object.entries(pilhaDadosAtiva)) {
        if (qtd > 0) partes.push(`${qtd}${dado}`);
    }
    const bonusInput = document.getElementById("bonus_dados");
    const bonus = bonusInput ? parseInt(bonusInput.value) || 0 : 0;
    if (bonus !== 0) partes.push(bonus > 0 ? `+${bonus}` : `${bonus}`);

    const inputFormula = document.getElementById("input_formula_rolagem");
    if (inputFormula) {
        if (partes.length > 0) {
            inputFormula.value = partes.join("+").replace(/\+\+/g, "+").replace(/^\+/, "");
        } else {
            inputFormula.value = "";
        }
    }
}

function parseFormulaRolagem(formula) {
    if (typeof formula !== "string") formula = "";

    // Remove todos os espaços em branco, independente da quantidade/posição
    const semEspacos = formula.replace(/\s+/g, "");

    // Campo vazio é válido e representa bônus zero
    if (semEspacos === "") {
        return { valido: true, valor: 0 };
    }

    // Aceita apenas sequências de números inteiros antecedidos por + ou -
    // Ex: "+5+2+3" ou "+5+3+2-1"
    const regexValido = /^([+\-]\d+)+$/;
    if (!regexValido.test(semEspacos)) {
        return { valido: false, valor: 0 };
    }

    // Soma cada termo assinado encontrado na fórmula
    const termos = semEspacos.match(/[+\-]\d+/g) || [];
    const valor = termos.reduce((soma, termo) => soma + parseInt(termo, 10), 0);

    return { valido: true, valor };
}

function aplicarFormulaRolagem() {
    // Chamada durante a digitação (oninput/onchange): apenas sincroniza o bônus
    // silenciosamente. Nenhuma notificação de erro é exibida aqui, evitando
    // poluição visual a cada alteração do campo. A validação com aviso ao
    // usuário só ocorre ao pressionar "Rolar Dados" (ver rolarPilhaDadosAtiva).
    const input = document.getElementById("input_formula_rolagem");
    if (!input) return;

    // Remove qualquer destaque de erro deixado por uma tentativa anterior de rolagem
    input.classList.remove("ui-border-danger");
    input.classList.add("ui-border");

    const resultado = parseFormulaRolagem(input.value);

    const bonusInput = document.getElementById("bonus_dados");
    if (bonusInput && resultado.valido) {
        bonusInput.value = resultado.valor;
    }
    // Se inválido, apenas não atualiza o bônus — sem notificar o usuário agora.
}

function ajustarCamposOperacao() {
    const op = document.querySelector("input[name='tipo_operacao_dados']:checked");
    if (!op) return;
    const panel = document.getElementById("painel_sub_opcoes");
    const opcoes = {
        Somatório: ["sub_explosao", "sub_evidenciar"],
        Rolar_Manter: ["sub_evidenciar", "sub_definir_sucesso"],
        Sucessos: ["sub_definir_sucesso", "sub_explosao"],
    };
    const visiveis = opcoes[op.value] || [];
    panel.classList.toggle("hidden", visiveis.length === 0);
    ["sub_explosao", "sub_evidenciar", "sub_definir_sucesso"].forEach((id) => {
        document.getElementById(id).classList.toggle("hidden", !visiveis.includes(id));
    });
    const evidenciar = document.getElementById("chk_evidenciar");
    if (evidenciar) {
        evidenciar.disabled = op.value === "Rolar_Manter";
        if (evidenciar.disabled) evidenciar.checked = true;
        alternarCamposEvidenciar();
    }
    const definirSucesso = document.getElementById("chk_definir_sucesso");
    if (definirSucesso) {
        definirSucesso.disabled = op.value === "Sucessos";
        if (definirSucesso.disabled) definirSucesso.checked = true;
        alternarCamposSucesso();
    }
}

function alternarCamposEvidenciar() {
    const chk = document.getElementById("chk_evidenciar");
    const panel = document.getElementById("painel_opcoes_evidenciar");
    if (chk && panel) panel.classList.toggle("hidden", !chk.checked);
}

function alternarCamposSucesso() {
    const chk = document.getElementById("chk_definir_sucesso");
    const panel = document.getElementById("painel_definir_sucesso_campos");
    if (chk && panel) panel.classList.toggle("hidden", !chk.checked);
}

function executarRolagemDiretaAtalho(formula) {
    const padrao = /^(\d+)d(\d+)([\+\-]\d+)?$/;
    const match = formula.match(padrao);
    if (!match) {
        mostrarToastNotificacao("Fórmula Inválida", "Use formato: 1d20 ou 3d6+5", "erro");
        return;
    }
    const qtd = parseInt(match[1]);
    const faces = parseInt(match[2]);
    const mod = match[3] ? parseInt(match[3]) : 0;
    const resultados = [];
    for (let i = 0; i < qtd; i++) {
        resultados.push({
            valor: Math.floor(Math.random() * faces) + 1,
            faces,
            explosivo: false,
            evidenciado: false,
            sucesso: false,
        });
    }
    const total = resultados.reduce((soma, dado) => soma + dado.valor, 0) + mod;
    const textoResultado = `Total: ${total}${formatarModificadorRolagem(mod)}`;
    mostrarToastNotificacao(
    "Rolagem: " + formula,
    `${textoResultado} (${formatarResultadosRolagem(resultados)})`,
    "sucesso",
    );
    adicionarLogHistorico(resultados, textoResultado);
}

function rolarPilhaDadosAtiva() {
    const chaves = Object.keys(pilhaDadosAtiva);
    if (chaves.length === 0) {
        mostrarToastNotificacao("Aviso", "Selecione pelo menos um dado.", "alerta");
        return;
    }

    // Valida a fórmula de bônus somente agora, ao pressionar "Rolar Dados".
    // É aqui (e apenas aqui) que uma notificação de fórmula inválida é exibida.
    const inputFormula = document.getElementById("input_formula_rolagem");
    const resultadoFormula = parseFormulaRolagem(inputFormula ? inputFormula.value : "");

    if (!resultadoFormula.valido) {
        mostrarToastNotificacao("Erro", "Fórmula de bônus inválida. Use apenas números precedidos de + ou -, Ex: +5+3-1", "erro");
        if (inputFormula) {
            inputFormula.classList.add("ui-border-danger");
            inputFormula.classList.remove("ui-border");
            setTimeout(() => {
                inputFormula.classList.remove("ui-border-danger");
                inputFormula.classList.add("ui-border");
            }, 2000);
        }
        return;
    }

    const op = document.querySelector("input[name='tipo_operacao_dados']:checked");
    const tipo = op ? op.value : "Somatório";
    const bonus = resultadoFormula.valor;
    if (inputFormula) {
        const bonusInput = document.getElementById("bonus_dados");
        if (bonusInput) bonusInput.value = bonus;
    }
    const usarSucesso = ["Rolar_Manter", "Sucessos"].includes(tipo)
    && document.getElementById("chk_definir_sucesso").checked;
    const usarExplosao = ["Somatório", "Sucessos"].includes(tipo)
    && document.getElementById("chk_explosao_dados").checked;
    const usarEvidenciar = tipo === "Rolar_Manter"
    || (tipo === "Somatório" && document.getElementById("chk_evidenciar").checked);
    const dadosRolados = [];
    const maximoExplosoesPorDado = 100;

    if (tipo === "Sucessos" && !usarSucesso) {
        mostrarToastNotificacao("Defina a margem", "Ative e configure Definir Sucesso para contar os dados bem-sucedidos.", "alerta");
        return;
    }
    const campoMargem = document.getElementById("valor_sucesso_minimo");
    if (tipo === "Sucessos" && !campoMargem.value.trim()) {
        mostrarToastNotificacao("Margem obrigatória", "Informe a margem de sucesso antes de rolar os dados.", "erro");
        return;
    }

    for (const [dado, qtd] of Object.entries(pilhaDadosAtiva)) {
        const faces = parseInt(dado.replace("d", ""));
        for (let i = 0; i < qtd; i++) {
            let valor = Math.floor(Math.random() * faces) + 1;
            dadosRolados.push({ valor, faces, explosivo: false, evidenciado: false, sucesso: false });
            let explosoes = 0;
            while (usarExplosao && valor === faces && explosoes < maximoExplosoesPorDado) {
                valor = Math.floor(Math.random() * faces) + 1;
                dadosRolados.push({ valor, faces, explosivo: true, evidenciado: false, sucesso: false });
                explosoes += 1;
            }
        }
    }

    const valores = dadosRolados.map((dado) => dado.valor);
    const manter = document.querySelector("input[name='manter_opcao']:checked");
    const manterMaior = !manter || manter.value === "Maior";
    const condicao = document.getElementById("condicao_sucesso").value;
    const margemSucesso = parseInt(document.getElementById("valor_sucesso_minimo").value, 10) || 0;
    const atendeMargem = (valor) => (
    (condicao === ">=" && valor >= margemSucesso)
    || (condicao === "=" && valor === margemSucesso)
    || (condicao === "<=" && valor <= margemSucesso)
    );

    let final = 0;
    let sucessos = 0;
    let textoResultado = "";
    if (tipo === "Sucessos") {
        dadosRolados.forEach((dado) => {
            dado.sucesso = atendeMargem(dado.valor);
            if (dado.sucesso) sucessos += 1;
        });
        final = sucessos;
        textoResultado = `Sucessos: <strong class="ui-text-positive">${final}</strong>`;
    } else if (tipo === "Somatório") {
        final = valores.reduce((a, b) => a + b, 0) + bonus;
        if (usarEvidenciar) {
            const indiceEvidenciado = valores.reduce((indice, valor, atual) => {
                if (indice === -1) return atual;
                return manterMaior ? (valor > valores[indice] ? atual : indice) : (valor < valores[indice] ? atual : indice);
            }, -1);
            if (indiceEvidenciado >= 0) dadosRolados[indiceEvidenciado].evidenciado = true;
        }
        textoResultado = `Total: ${final}`;
    } else if (tipo === "Rolar_Manter") {
        const indiceMantido = valores.reduce((indice, valor, atual) => {
            if (indice === -1) return atual;
            return manterMaior ? (valor > valores[indice] ? atual : indice) : (valor < valores[indice] ? atual : indice);
        }, -1);
        final = valores[indiceMantido];
        final += bonus;
        dadosRolados[indiceMantido].evidenciado = true;
        if (usarSucesso) {
            const sucesso = atendeMargem(final);
            sucessos = sucesso ? 1 : 0;
            dadosRolados.forEach((dado) => {
                dado.sucesso = atendeMargem(dado.valor);
            });
            textoResultado = sucesso
            ? `Sucesso: <strong class="ui-text-positive">${final}</strong>`
            : `Falha: <strong class="ui-text-danger">${final}</strong>`;
        } else {
            textoResultado = `Resultado: <strong class="ui-text-positive">${final}</strong>`;
        }
    }

    textoResultado += formatarModificadorRolagem(bonus);
    const listaValores = formatarResultadosRolagem(dadosRolados);
    mostrarToastNotificacao("Rolagem Realizada!", `${textoResultado} (${listaValores})`, "sucesso");
    adicionarLogHistorico(dadosRolados, textoResultado);
    fecharDiceRoller();
    limparPilhaDados();
}

function formatarResultadosRolagem(resultados) {
    return resultados.map((dado) => {
        const cor = dado.explosivo
        ? "ui-text-accent"
        : dado.sucesso || dado.evidenciado
        ? "ui-text-positive"
        : "ui-text-muted";
        const peso = dado.explosivo || dado.sucesso || dado.evidenciado ? "font-black" : "font-normal";
        return `<span class="${cor} ${peso}">${dado.valor}</span>`;
    }).join(", ");
}

function formatarModificadorRolagem(modificador) {
    if (!modificador) return "";
    const sinal = modificador > 0 ? "+" : "";
    return ` <span class="text-xs font-medium ui-text-muted">(Modificador: ${sinal}${modificador})</span>`;
}

function adicionarLogHistorico(resultados, textoResultado) {
    const container = document.getElementById("lista_historico_rolagens");
    if (!container) return;
    const placeholder = container.querySelector("[data-historico-vazio]");
    if (placeholder) placeholder.remove();

    const item = document.createElement("div");
    item.className = "p-4 ui-surface border ui-border rounded-2xl space-y-2";
    item.innerHTML = `
 <div class="flex items-center">
 <span class="text-xs font-mono ui-text-muted font-bold">Rolagem</span>
 </div>
 <p class="text-sm font-bold text-white">${textoResultado}</p>
 <p class="text-[10px] font-mono">Valores: [${formatarResultadosRolagem(resultados)}]</p>
 `;
    container.insertBefore(item, container.firstChild);
}

window.addEventListener("DOMContentLoaded", () => {
    ajustarCamposOperacao();
    alternarCamposEvidenciar();
    alternarCamposSucesso();
});
