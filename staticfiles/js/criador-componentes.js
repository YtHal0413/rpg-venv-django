// Bloco: cria??o e atualiza??o visual dos componentes da ficha.

function renderizarConfiguradorEstrutura() {
    // Placeholder compatível com chamadas existentes.
    // Esta função mantém a API e evita erros quando a estrutura de configurações ainda não precisa ser atualizada dinamicamente.
}

function obterRotuloComponente(comp, tipo) {
    const ehComponenteAtributo = tipo === "AtributoSimples" || tipo === "AtributoDuplo" || tipo === "AtributoComplexo";
    if (ehComponenteAtributo) {
        if (typeof comp?.nomeAtributo === "string" && comp.nomeAtributo.trim() !== "") return comp.nomeAtributo;
        return "";
    }
    if (typeof comp?.rotulo === "string" && comp.rotulo.trim() !== "") return comp.rotulo;
    return "";
}

function criarBotaoExcluirComponente(numColuna, secaoId, compId, className = "p-1.5 ui-text-muted ui-hover-danger-text rounded-lg ui-hover-danger-soft transition") {
    const btnDel = document.createElement("button");
    btnDel.className = className;
    btnDel.textContent = "×";
    btnDel.onclick = () => {
        removerComponenteFicha(numColuna, secaoId, compId);
        agendarSalvamento();
    };
    return btnDel;
}

function obterValorNumericoContador(el) {
    if (!el) return 0;
    const texto = (el.value ?? el.textContent ?? "").toString();
    return parseInt(texto.replace(/\D/g, ""), 10) || 0;
}

function aplicarCorContador(compId, cor) {
    const bar = document.getElementById(`contador_bar_${compId}`);
    if (bar) bar.style.backgroundColor = cor;
}

function atualizarVisualContador(compId, comp) {
    const bar = document.getElementById(`contador_bar_${compId}`);
    const curEl = document.getElementById(`contador_cur_${compId}`);
    const maxEl = document.getElementById(`contador_max_${compId}`);

    if (!bar || !curEl || !maxEl) return;

    const cur = Math.max(0, obterValorNumericoContador(curEl));
    const max = Math.max(1, obterValorNumericoContador(maxEl) || 1);

    comp.valorAtual = cur;
    comp.valorMaximo = max;

    if (curEl.tagName === "INPUT") {
        curEl.value = cur;
    } else {
        curEl.textContent = cur;
    }

    if (maxEl.tagName === "INPUT") {
        maxEl.value = max;
    } else {
        maxEl.textContent = max;
    }

    const pct = Math.min((cur / max) * 100, 100);
    bar.style.width = `${pct}%`;
    aplicarCorContador(compId, comp.corSeletor || "#4A4E69");
}

function atualizarRotuloComponente(numColuna, secaoId, compId, valor, tipo) {
    const campo = tipo === "AtributoSimples" || tipo === "AtributoDuplo" || tipo === "AtributoComplexo" ? "nomeAtributo" : "rotulo";
    atualizarValorComponente(numColuna, secaoId, compId, campo, valor);
}

function renderizarComponenteFicha(numColuna, secaoId, comp, tipo) {
    const div = document.createElement("div");
    div.className = "p-3 rounded-xl ui-component border ui-border flex flex-col justify-between";
    const editavel = estadoFicha.modo === "Edição";
    const modoJogo = estadoFicha.modo === "Jogo";

    const info = document.createElement("div");
    info.className = "flex-grow space-y-1 overflow-hidden";

    const rotuloAtual = obterRotuloComponente(comp, tipo);

    const inputRotulo = document.createElement(editavel || tipo === "AtributoComplexo" ? "input" : "span");
    if (inputRotulo.tagName === "INPUT") {
        inputRotulo.type = "text";
        inputRotulo.value = rotuloAtual;
        inputRotulo.className = "bg-transparent border-b ui-border ui-focus-border focus:outline-none text-sm font-bold text-white " + (tipo === "Contador" ? "w-[15.5rem] mb-3" : "w-full mb-2");
        inputRotulo.placeholder = "Rótulo";
        inputRotulo.onchange = (e) => {
            atualizarRotuloComponente(numColuna, secaoId, comp.id, e.target.value, tipo);
            agendarSalvamento();
        };
        if (modoJogo && tipo === "AtributoComplexo") {
            inputRotulo.disabled = true;
            inputRotulo.className += " text-center";
        }
    } else {
        inputRotulo.className = "text-sm font-bold ui-text-copy block truncate mb-2 text-center";
        inputRotulo.textContent = rotuloAtual;
    }

    const acao = document.createElement("div");
    acao.className = "flex items-center space-x-2 flex-shrink-0";

    switch(tipo) {
        case "AtributoSimples":
        div.className = "atributo-card relative flex flex-col justify-between";
        info.className = "flex-grow space-y-1 overflow-hidden mt-[0.6rem] items-end justify-between gap-2";

        const inpSimples = document.createElement("input");
        inpSimples.type = "number";
        inpSimples.value = comp.valorAtributo || 0;
        inpSimples.className = "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ui-surface border ui-border rounded-2xl text-center text-xl font-black p-2 text-white focus:outline-none ui-focus-border w-[75px] aspect-square";
        inpSimples.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "valorAtributo", parseInt(e.target.value) || 0);
            agendarSalvamento();
        };
        if (!editavel) inpSimples.disabled = true;

        info.appendChild(inpSimples);
        info.appendChild(inputRotulo);

        if (editavel) {
            const btnDel = document.createElement("button");
            btnDel.className = "absolute top-2.5 left-2.5 p-1.5 ui-text-muted ui-hover-danger-text rounded-lg ui-hover-danger-soft transition flex items-center justify-center";
            btnDel.textContent = "×";
            btnDel.onclick = () => {
                removerComponenteFicha(numColuna, secaoId, comp.id);
                agendarSalvamento();
            };
            div.appendChild(btnDel);
        }
        break;

        case "Contador":
        div.className = "p-3 rounded-xl ui-component border ui-border flex flex-col justify-between";
        if (editavel) {
            div.classList.add("relative");
        }
        const divContador = document.createElement("div");
        divContador.className = "flex flex-col gap-2 w-full";

        info.appendChild(inputRotulo);

        const corSeletor = comp.corSeletor || "#4A4E69";
        const valorAtual = Number(comp.valorAtual) || 10;
        const valorMaximo = Number(comp.valorMaximo) || 10;

        const containerBarra = document.createElement("div");
        containerBarra.className = "relative w-full h-[30px] border-[2px] ui-border rounded-full ui-surface flex items-center justify-between overflow-hidden";

        const barraPreenchimento = document.createElement("div");
        barraPreenchimento.id = `contador_bar_${comp.id}`;
        barraPreenchimento.className = "absolute top-0 left-0 h-full transition-all duration-200 ease-out z-10";
        barraPreenchimento.style.backgroundColor = corSeletor;
        barraPreenchimento.style.width = `${Math.min((valorAtual / Math.max(1, valorMaximo)) * 100, 100)}%`;

        const camadaInterativa = document.createElement("div");
        camadaInterativa.className = "absolute inset-0 flex justify-center px-4 z-20";

        const indicadores = document.createElement("div");
        indicadores.className = "text-white text-base font-medium flex items-center gap-1.5";

        const curEl = document.createElement("input");
        curEl.id = `contador_cur_${comp.id}`;
        curEl.type = "number";
        curEl.min = "0";
        curEl.step = "1";
        curEl.className = "bg-transparent border-0 text-white font-semibold text-center w-[50px] outline-none border-b border-transparent ui-hover-border-accent ui-focus-border [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none";
        curEl.value = String(valorAtual);
        curEl.oninput = () => {
            atualizarVisualContador(comp.id, comp);
        };
        curEl.onblur = () => {
            let val = Math.max(0, obterValorNumericoContador(curEl));
            curEl.value = String(val);
            comp.valorAtual = val;
            atualizarVisualContador(comp.id, comp);
            agendarSalvamento();
        };
        curEl.onkeydown = (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                curEl.blur();
            }
        };

        const separador = document.createElement("span");
        separador.textContent = "/";

        const maxEl = document.createElement("input");
        maxEl.id = `contador_max_${comp.id}`;
        maxEl.type = "number";
        maxEl.min = "1";
        maxEl.step = "1";
        maxEl.className = "bg-transparent border-0 text-white font-semibold text-center w-[50px] outline-none border-b border-transparent ui-hover-border-accent ui-focus-border [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none";
        maxEl.value = String(valorMaximo);
        maxEl.oninput = () => {
            atualizarVisualContador(comp.id, comp);
        };
        maxEl.onblur = () => {
            let val = Math.max(1, obterValorNumericoContador(maxEl));
            maxEl.value = String(val);
            comp.valorMaximo = val;
            atualizarVisualContador(comp.id, comp);
            agendarSalvamento();
        };
        maxEl.onkeydown = (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                maxEl.blur();
            }
        };

        indicadores.appendChild(curEl);
        indicadores.appendChild(separador);
        indicadores.appendChild(maxEl);

        camadaInterativa.appendChild(indicadores);

        containerBarra.appendChild(barraPreenchimento);
        containerBarra.appendChild(camadaInterativa);
        divContador.appendChild(containerBarra);

        if (editavel) {
            const seletorCores = document.createElement("div");
            seletorCores.className = "selector-cores";
            const coresPadrao = ["#3b373c", "#946627", "#e72c7a", "#eb2b36", "#f97316", "#d3ac00", "#00ac3f", "#00bb92", "#0e5ee9", "#8b41b6"];
            coresPadrao.forEach(cor => {
                const btnCor = document.createElement("button");
                btnCor.style.backgroundColor = cor;
                btnCor.onclick = () => {
                    atualizarValorComponente(numColuna, secaoId, comp.id, "corSeletor", cor);
                    aplicarCorContador(comp.id, cor);
                    agendarSalvamento();
                    Array.from(seletorCores.children).forEach(child => child.classList.remove("selecionado"));
                    btnCor.classList.add("selecionado");
                };
                if (corSeletor === cor) btnCor.classList.add("selecionado");
                seletorCores.appendChild(btnCor);
            });
            divContador.appendChild(seletorCores);
        }

        atualizarVisualContador(comp.id, comp);

        acao.appendChild(divContador);

        if (editavel) {
            const btnDel = document.createElement("button");
            btnDel.className = "absolute top-[0.5rem] left-[17rem] p-1.5 ui-text-muted ui-hover-danger-text rounded-lg ui-hover-danger-soft transition flex items-center justify-center";
            btnDel.textContent = "×";
            btnDel.onclick = () => {
                removerComponenteFicha(numColuna, secaoId, comp.id);
                agendarSalvamento();
            };
            div.appendChild(btnDel);
        }
        break;

        case "AtributoDuplo":
        div.className = "atributo-card relative flex flex-col justify-between";

        const linhaValoresDuplo = document.createElement("div");
        linhaValoresDuplo.className = "flex items-center flex-col";

        const inpPequeno = document.createElement("input");
        inpPequeno.type = "number";
        inpPequeno.value = comp.valorPequeno || 0;
        inpPequeno.className = "[&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none text-center ui-focus-border h-[6px] w-[45px] aspect-square bg-transparent border-b ui-border ui-focus-border focus:outline-none text-xs font-bold text-white mb-1";
        inpPequeno.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "valorPequeno", parseInt(e.target.value) || 0);
            agendarSalvamento();
        };
        if (!editavel) inpPequeno.disabled = true;

        const inpGrande = document.createElement("input");
        inpGrande.type = "number";
        inpGrande.value = comp.valorGrande || 0;
        inpGrande.className = "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ui-surface border ui-border rounded-2xl text-center text-lg font-black p-2 text-white focus:outline-none ui-focus-border w-[65px] aspect-square";
        inpGrande.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "valorGrande", parseInt(e.target.value) || 0);
            agendarSalvamento();
        };
        if (!editavel) inpGrande.disabled = true;

        linhaValoresDuplo.appendChild(inpPequeno);
        linhaValoresDuplo.appendChild(inpGrande);
        info.appendChild(linhaValoresDuplo);
        info.appendChild(inputRotulo);

        if (editavel) {
            const btnDel = document.createElement("button");
            btnDel.className = "absolute top-2.5 left-2.5 p-1.5 ui-text-muted ui-hover-danger-text rounded-lg ui-hover-danger-soft transition flex items-center justify-center";
            btnDel.textContent = "×";
            btnDel.onclick = () => {
                removerComponenteFicha(numColuna, secaoId, comp.id);
                agendarSalvamento();
            };
            div.appendChild(btnDel);
        }
        break;

        case "AtributoComplexo":
        div.className = "relative flex flex-row p-[1rem] h-[100px] text-center ui-component border ui-border rounded-2xl ui-surface items-center";

        info.className = "flex flex-col w-[6rem] mr-[10px] overflow-hidden";
        if (editavel) {
            inputRotulo.className = "bg-transparent border-b ui-border ui-focus-border focus:outline-none text-sm font-bold text-white w-full";
            inputRotulo.placeholder = "Rótulo";
        }

        const subtituloComp = document.createElement("input");
        subtituloComp.type = "text";
        subtituloComp.value = comp.subtituloAnotacao || "";
        subtituloComp.placeholder = "Sub-rotulo";
        subtituloComp.className = "bg-transparent ui-border ui-focus-border focus:outline-none text-xs font-bold mt-[5px] w-full";
        subtituloComp.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "subtituloAnotacao", e.target.value);
            agendarSalvamento();
            if (modoJogo) {
                subtituloComp.style.display = (e.target.value && e.target.value.trim() !== "") ? "block" : "none";
            }
        };
        if (!editavel) {
            subtituloComp.disabled = true;
            subtituloComp.className += " text-center";
        }
        if (modoJogo) {
            if (!subtituloComp.value || subtituloComp.value.trim() === "") {
                subtituloComp.style.display = "none";
            } else {
                subtituloComp.style.display = "block";
            }
        }

        info.appendChild(inputRotulo);
        info.appendChild(subtituloComp);

        const divComplexo = document.createElement("div");
        divComplexo.className = "flex flex-col gap-3 w-full";

        const valoresComplexos = document.createElement("div");
        valoresComplexos.className = "flex items-center gap-1 flex-wrap";

        const inpBase = document.createElement("input");
        inpBase.type = "number";
        inpBase.value = comp.valorBase || 0;
        inpBase.className = "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ui-surface border ui-border rounded-2xl text-center text-xs p-2 focus:outline-none ui-focus-border aspect-square w-[40px]";
        inpBase.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "valorBase", parseInt(e.target.value) || 0);
            recalcularTotalComplexo(numColuna, secaoId, comp.id);
            agendarSalvamento();
        };
        inpBase.disabled = !editavel;

        const inpBonus = document.createElement("input");
        inpBonus.type = "number";
        inpBonus.value = comp.valorBonus || 0;
        inpBonus.className = "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ui-surface border ui-border rounded-2xl text-center text-xs p-2 focus:outline-none ui-focus-border aspect-square w-[40px]";
        inpBonus.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "valorBonus", parseInt(e.target.value) || 0);
            recalcularTotalComplexo(numColuna, secaoId, comp.id);
            agendarSalvamento();
        };
        inpBonus.disabled = !editavel;

        const inpOutros = document.createElement("input");
        inpOutros.type = "number";
        inpOutros.value = comp.valorOutros || 0;
        inpOutros.className = "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ui-surface border ui-border rounded-2xl text-center text-xs p-2 focus:outline-none ui-focus-border aspect-square w-[40px]";
        inpOutros.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "valorOutros", parseInt(e.target.value) || 0);
            recalcularTotalComplexo(numColuna, secaoId, comp.id);
            agendarSalvamento();
        };
        inpOutros.disabled = !editavel;

        const spanTotal = document.createElement("span");
        spanTotal.id = `total_complexo_${comp.id}`;
        spanTotal.className = "text-xs font-black ui-text-accent mx-[0.7rem]";
        spanTotal.textContent = (Number(comp.valorBase) || 0) + (Number(comp.valorBonus) || 0) + (Number(comp.valorOutros) || 0);

        valoresComplexos.appendChild(inpBase);
        valoresComplexos.appendChild(inpBonus);
        valoresComplexos.appendChild(inpOutros);
        valoresComplexos.appendChild(document.createTextNode(" = "));
        valoresComplexos.appendChild(spanTotal);

        divComplexo.appendChild(valoresComplexos);
        acao.className = "flex items-center flex-shrink-0";
        acao.appendChild(divComplexo);
        if (editavel) {
            acao.appendChild(criarBotaoExcluirComponente(numColuna, secaoId, comp.id, "absolute left-[16.5rem] bottom-[0.3rem] p-1.5 ui-text-muted ui-hover-danger-text rounded-lg ui-hover-danger-soft transition flex items-center justify-center"));
        }
        break;

        case "Checkbox":
        div.className = "p-3 rounded-xl ui-component border ui-border flex flex-row justify-between items-center";
        info.className = "flex-grow space-y-1 overflow-hidden";

        if (inputRotulo.tagName === "INPUT") {
            inputRotulo.className = "bg-transparent border-b ui-border ui-focus-border focus:outline-none text-sm font-bold text-white w-full";
        } else {
            inputRotulo.className = "text-sm font-bold ui-text-copy block truncate text-left";
        }

        info.appendChild(inputRotulo);

        const inpCheck = document.createElement("input");
        inpCheck.type = "checkbox";
        inpCheck.checked = comp.estaMarcado || false;
        inpCheck.className = "w-4 h-4 rounded ui-text-accent focus:ring-0 focus:ring-offset-0 bg-transparent ui-border";
        inpCheck.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "estaMarcado", e.target.checked);
            agendarSalvamento();
        };

        acao.className = "flex items-center space-x-2 flex-shrink-0";
        acao.appendChild(inpCheck);

        if (editavel) {
            acao.appendChild(criarBotaoExcluirComponente(numColuna, secaoId, comp.id));
        }
        break;

        case "InformacaoCurta":
        div.className = "p-3 rounded-xl ui-component border ui-border flex flex-col justify-between";
        if (inputRotulo.tagName === "INPUT") {
            inputRotulo.className = "bg-transparent border-b ui-border ui-focus-border focus:outline-none text-sm font-bold text-white w-full";
        } else {
            inputRotulo.className = "text-sm font-bold ui-text-copy block truncate text-left mb-2";
        }
        info.appendChild(inputRotulo);

        const inpTexto = document.createElement("input");
        inpTexto.type = "text";
        inpTexto.value = comp.campoTexto || "";
        inpTexto.placeholder = "Texto Curto";
        inpTexto.className = "ui-surface border ui-border rounded-lg px-2 py-1 text-xs text-white focus:outline-none ui-focus-border flex-grow text-left";
        inpTexto.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "campoTexto", e.target.value);
            agendarSalvamento();
        };
        if (!editavel) inpTexto.disabled = true;
        acao.appendChild(inpTexto);
        if (editavel) {
            acao.appendChild(criarBotaoExcluirComponente(numColuna, secaoId, comp.id));
        }
        break;

        case "AnotacaoSimples":
        div.className = "ui-surface border ui-border rounded-2xl p-3";

        const divAnotSimples = document.createElement("div");
        divAnotSimples.className = "flex flex-col gap-2 w-full";

        const cabecalhoAnotSimples = document.createElement("div");
        cabecalhoAnotSimples.className = "flex items-center gap-2";

        const descSimples = document.createElement("input");
        descSimples.type = "text";
        descSimples.value = comp.rotulo || "";
        descSimples.placeholder = "Título da anotação";
        descSimples.className = "bg-transparent border-b ui-border ui-focus-border focus:outline-none text-sm font-bold text-white w-full";
        descSimples.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "rotulo", e.target.value);
            agendarSalvamento();
        };
        descSimples.disabled = !editavel;
        cabecalhoAnotSimples.appendChild(descSimples);

        const areaSimples = document.createElement("textarea");
        areaSimples.value = comp.descricao || comp.texto || "";
        areaSimples.placeholder = "Descrição...";
        areaSimples.rows = 3;
        areaSimples.className = "auto-altura ui-surface border ui-border rounded-2xl p-3 text-xs ui-text-copy focus:outline-none ui-focus-border w-full resize-vertical";
        areaSimples.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "descricao", e.target.value);
            agendarSalvamento();
        };
        areaSimples.disabled = !editavel;

        divAnotSimples.appendChild(cabecalhoAnotSimples);
        divAnotSimples.appendChild(areaSimples);
        info.appendChild(divAnotSimples);
        if (editavel) {
            acao.appendChild(criarBotaoExcluirComponente(numColuna, secaoId, comp.id));
        }
        break;

        case "AnotacaoCheckbox":
        const divAnotCheck = document.createElement("div");
        divAnotCheck.className = "flex flex-col gap-2 w-full";

        const cabecalhoAnot = document.createElement("div");
        cabecalhoAnot.className = "colapsavel-cabecalho";

        const descCheck = document.createElement("input");
        descCheck.type = "text";
        descCheck.value = comp.rotulo || "";
        descCheck.placeholder = "Título da anotação";
        descCheck.className = "bg-transparent border-b ui-border ui-focus-border focus:outline-none text-sm font-bold text-white w-[80%]";
        descCheck.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "rotulo", e.target.value);
            agendarSalvamento();
        };
        descCheck.disabled = !editavel;
        cabecalhoAnot.appendChild(descCheck);

        const chkAnot = document.createElement("input");
        chkAnot.type = "checkbox";
        chkAnot.checked = comp.estaMarcado || false;
        chkAnot.className = "w-[17px] h-[17px] rounded ui-text-accent focus:ring-0 focus:ring-offset-0 bg-transparent ui-border";
        chkAnot.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "estaMarcado", e.target.checked);
            agendarSalvamento();
        };
        chkAnot.disabled = false;
        cabecalhoAnot.appendChild(chkAnot);

        const toggleAnot = document.createElement("button");
        toggleAnot.type = "button";
        toggleAnot.className = "colapsavel-toggle";
        toggleAnot.textContent = "•••";
        cabecalhoAnot.appendChild(toggleAnot);

        const conteudoAnot = document.createElement("div");
        conteudoAnot.className = "colapsavel-conteudo";
        const textAreaAt = document.createElement("textarea");
        textAreaAt.value = comp.descricao || "";
        textAreaAt.placeholder = "Descrição longa...";
        textAreaAt.rows = 3;
        textAreaAt.className = "auto-altura ui-surface border ui-border rounded-2xl p-3 text-xs ui-text-copy focus:outline-none ui-focus-border w-full resize-vertical";
        textAreaAt.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "descricao", e.target.value);
            agendarSalvamento();
        };
        textAreaAt.disabled = !editavel;
        conteudoAnot.appendChild(textAreaAt);
        toggleAnot.onclick = () => {
            conteudoAnot.classList.toggle("aberto");
        };

        divAnotCheck.appendChild(cabecalhoAnot);
        divAnotCheck.appendChild(conteudoAnot);
        info.appendChild(divAnotCheck);
        if (editavel) {
            acao.appendChild(criarBotaoExcluirComponente(numColuna, secaoId, comp.id));
        }
        break;

        case "AnotacaoDetalhada":
        const divConteudoAnotDet = document.createElement("div");
        divConteudoAnotDet.className = "flex flex-col gap-2 w-full";

        const cabecalhoAnotDet = document.createElement("div");
        cabecalhoAnotDet.className = "flex flex-row items-center justify-between gap-1";

        const blocoInputsAnotDet = document.createElement("div");
        blocoInputsAnotDet.className = "w-[80%]";

        const inputTituloAnotDet = document.createElement("input");
        inputTituloAnotDet.type = "text";
        inputTituloAnotDet.value = comp.rotulo || "";
        inputTituloAnotDet.placeholder = "Título da anotação";
        inputTituloAnotDet.className = "bg-transparent border-b ui-border ui-focus-border focus:outline-none text-sm font-bold text-white w-full";
        inputTituloAnotDet.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "rotulo", e.target.value);
            agendarSalvamento();
        };
        inputTituloAnotDet.disabled = !editavel;
        blocoInputsAnotDet.appendChild(inputTituloAnotDet);

        const inputSubtituloAnotDet = document.createElement("input");
        inputSubtituloAnotDet.type = "text";
        inputSubtituloAnotDet.value = comp.anotacaoExtra || "";
        inputSubtituloAnotDet.placeholder = "Texto adicional";
        inputSubtituloAnotDet.className = "bg-transparent ui-border ui-focus-border focus:outline-none text-xs font-bold w-full";
        inputSubtituloAnotDet.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "anotacaoExtra", e.target.value);
            agendarSalvamento();
        };
        inputSubtituloAnotDet.disabled = !editavel;
        blocoInputsAnotDet.appendChild(inputSubtituloAnotDet);

        cabecalhoAnotDet.appendChild(blocoInputsAnotDet);

        const toggleAnotDet = document.createElement("button");
        toggleAnotDet.type = "button";
        toggleAnotDet.className = "colapsavel-toggle";
        toggleAnotDet.textContent = "•••";
        cabecalhoAnotDet.appendChild(toggleAnotDet);

        const conteudoAnotDet = document.createElement("div");
        conteudoAnotDet.className = "colapsavel-conteudo";

        const areaDescDet = document.createElement("textarea");
        areaDescDet.value = comp.descricao || "";
        areaDescDet.placeholder = "Descrição...";
        areaDescDet.rows = 2;
        areaDescDet.className = "auto-altura ui-surface border ui-border rounded-2xl p-3 text-xs ui-text-copy focus:outline-none ui-focus-border w-full resize-vertical";
        areaDescDet.onchange = (e) => {
            atualizarValorComponente(numColuna, secaoId, comp.id, "descricao", e.target.value);
            agendarSalvamento();
        };
        if (!editavel) areaDescDet.disabled = true;
        conteudoAnotDet.appendChild(areaDescDet);
        toggleAnotDet.onclick = () => {
            conteudoAnotDet.classList.toggle("aberto");
        };

        divConteudoAnotDet.appendChild(cabecalhoAnotDet);
        divConteudoAnotDet.appendChild(conteudoAnotDet);
        info.appendChild(divConteudoAnotDet);
        if (editavel) {
            acao.appendChild(criarBotaoExcluirComponente(numColuna, secaoId, comp.id));
        }
        break;

        default:
        const spanPlaceholder = document.createElement("span");
        spanPlaceholder.className = "text-xs ui-text-muted";
        spanPlaceholder.textContent = comp.rotulo || "Componente";
        acao.appendChild(spanPlaceholder);
        if (editavel) {
            acao.appendChild(criarBotaoExcluirComponente(numColuna, secaoId, comp.id));
        }
        break;
    }

    div.appendChild(info);
    div.appendChild(acao);
    return div;
}
