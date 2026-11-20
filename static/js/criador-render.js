// Bloco: atualiza a interface a partir do estado atual da ficha.
function renderizarFichaCompleta() {
    const inputNome = document.getElementById("nome_personagem_topo");
    if (inputNome) {
        inputNome.value = estadoFicha.nome;
        inputNome.readOnly = !estadoFicha.podeEditar;
    }
    const inputSubtitulo = document.getElementById("subtitulo_card");
    if (inputSubtitulo) {
        inputSubtitulo.value = estadoFicha.subtitulo;
        inputSubtitulo.readOnly = !estadoFicha.podeEditar;
    }

    const img = document.getElementById('avatar_imagem');
    const placeholder = document.getElementById('avatar_placeholder');
    if (estadoFicha.avatar) {
        if (img) {
            img.src = estadoFicha.avatar;
            img.classList.remove('hidden');
        }
        if (placeholder) placeholder.classList.add('hidden');
    } else {
        if (img) img.classList.add('hidden');
        if (placeholder) placeholder.classList.remove('hidden');
    }

    for (let c = 1; c <= 3; c++) {
        renderizarColuna(c);
    }
    verificarOcultamentoColunasVazias();
    const visibilidadeRadios = document.querySelectorAll("input[name='visibilidade_ficha']");
    if (visibilidadeRadios) {
        visibilidadeRadios.forEach(radio => {
            const isChecked = radio.value === estadoFicha.visibilidade;
            radio.checked = isChecked;
            radio.defaultChecked = isChecked;
            if (!estadoFicha.podeEditar) {
                radio.disabled = true;
            }
        });
    }
    const statusVisibilidade = document.getElementById("status-visibilidade");
    if (statusVisibilidade) {
        statusVisibilidade.textContent = estadoFicha.visibilidade === "mestres" ? "Mestres" : "Todos";
    }
    renderizarConfiguradorEstrutura();
}

function renderizarColuna(numColuna) {
    const coluna = estadoFicha.colunas[numColuna];
    const conteinerAbas = document.getElementById(`abas_coluna_${numColuna}`);
    const conteinerSecoes = document.getElementById(`secoes_coluna_${numColuna}`);

    if (!coluna || !coluna.ativa) {
        document.getElementById(`coluna_${numColuna}`).classList.add("hidden");
        return;
    }
    document.getElementById(`coluna_${numColuna}`).classList.remove("hidden");

    if (coluna.abas && coluna.abas.length > 0 && (coluna.abaAtivaId == null || !coluna.abas.some(a => a.id == coluna.abaAtivaId))) {
        coluna.abaAtivaId = coluna.abas[0].id;
    }

    conteinerAbas.innerHTML = "";
    if (!coluna.abas || coluna.abas.length === 0) {
        conteinerAbas.innerHTML = `<p class="text-xs ui-text-muted self-center font-bold uppercase tracking-wider py-1.5">Coluna Vazia</p>`;
        conteinerSecoes.innerHTML = `<p class="text-xs ui-text-muted text-center py-12 sem-conteudo-coluna">Crie uma aba para ativar esta coluna.</p>`;
        return;
    }

    coluna.abas.forEach(aba => {
        const ativo = aba.id == coluna.abaAtivaId;
        const ehAbaPadrao = aba.ehPadrao === true || aba.titulo === "Geral";
        const wrapper = document.createElement("div");
        wrapper.className = "flex items-center space-x-1";

        const btn = document.createElement("button");
        btn.className = `px-3.5 py-2 rounded-lg text-xs font-bold transition ${ativo ? 'ui-action ui-button-copy' : 'ui-text-copy ui-hover-heading ui-component'}`;
        btn.textContent = aba.titulo;
        btn.onclick = () => alternarAbaColuna(numColuna, aba.id);
        wrapper.appendChild(btn);

        if (estadoFicha.modo === "Edição" && !ehAbaPadrao) {
            const btnDel = document.createElement("button");
            btnDel.className = "p-1 ui-text-muted ui-hover-danger-text transition text-[10px]";
            btnDel.textContent = "×";
            btnDel.onclick = (e) => {
                e.stopPropagation();
                removerAbaColuna(numColuna, aba.id);
            };
            wrapper.appendChild(btnDel);
        }
        conteinerAbas.appendChild(wrapper);
    });

    renderizarSecoesAbaAtiva(numColuna);
}

function renderizarSecoesAbaAtiva(numColuna) {
    const coluna = estadoFicha.colunas[numColuna];
    const conteinerSecoes = document.getElementById(`secoes_coluna_${numColuna}`);
    conteinerSecoes.innerHTML = "";

    let abaAtiva = coluna.abas.find(a => a.id == coluna.abaAtivaId);
    if (!abaAtiva && coluna.abas && coluna.abas.length > 0) {
        coluna.abaAtivaId = coluna.abas[0].id;
        abaAtiva = coluna.abas[0];
    }

    if (numColuna === 1 && abaAtiva && (abaAtiva.ehPadrao === true || abaAtiva.titulo === "Geral")) {
        const cardPerfil = document.createElement("div");
        cardPerfil.id = "card_perfil_personagem";
        cardPerfil.className = "p-5 ui-gradient-surface border ui-border rounded-2xl flex items-center space-x-5 relative overflow-hidden group";

        const divAvatar = document.createElement("div");
        divAvatar.className = "relative w-28 h-28 rounded-2xl overflow-hidden border-2 ui-border-accent ui-surface flex-shrink-0";

        const img = document.createElement("img");
        img.id = "avatar_imagem";
        img.className = estadoFicha.avatar ? "w-full h-full object-cover" : "w-full h-full object-cover hidden";
        img.src = estadoFicha.avatar || "";
        img.alt = "Avatar";
        divAvatar.appendChild(img);

        const placeholder = document.createElement("div");
        placeholder.id = "avatar_placeholder";
        placeholder.className = estadoFicha.avatar ? "hidden" : "w-full h-full flex items-center justify-center ui-gradient-component";
        placeholder.innerHTML = `<svg class="w-12 h-12 ui-text-accent" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
 <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
 </svg>`;
        divAvatar.appendChild(placeholder);

        if (estadoFicha.modo === "Edição") {
            const divControles = document.createElement("div");
            divControles.className = "absolute inset-0 ui-overlay flex flex-col items-center justify-center p-1 gap-1.5";
            divControles.innerHTML = `
 <button onclick="mudarFoto()" class="text-[9px] font-bold ui-action ui-hover-accent ui-button-copy py-1 px-1.5 rounded-md w-full text-center transition">TROCAR FOTO</button>
 <button onclick="removerFoto()" class="text-[9px] font-bold ui-danger ui-hover-danger text-white py-1 px-1.5 rounded-md w-full text-center transition">REMOVER</button>
 `;
            divAvatar.appendChild(divControles);
        }

        cardPerfil.appendChild(divAvatar);

        const divTexto = document.createElement("div");
        divTexto.className = "space-y-1 overflow-hidden flex-1";

        const inputNome = document.createElement("input");
        inputNome.id = "nome_personagem_topo";
        inputNome.type = "text";
        inputNome.value = estadoFicha.nome;
        inputNome.className = "text-lg font-black tracking-tight text-white bg-transparent border-b ui-border ui-focus-border outline-none w-full ui-placeholder";
        inputNome.placeholder = "Nome do Personagem";
        divTexto.appendChild(inputNome);

        const inputSubtitulo = document.createElement("input");
        inputSubtitulo.id = "subtitulo_card";
        inputSubtitulo.type = "text";
        inputSubtitulo.value = estadoFicha.subtitulo;
        inputSubtitulo.className = "text-sm ui-text-muted truncate tracking-tight bg-transparent ui-focus-border outline-none w-full ui-placeholder";
        inputSubtitulo.placeholder = "Aspecto";
        divTexto.appendChild(inputSubtitulo);

        cardPerfil.appendChild(divTexto);
        conteinerSecoes.appendChild(cardPerfil);

        inicializarEventosFicha();
    }

    if (!abaAtiva || !abaAtiva.secoes || abaAtiva.secoes.length === 0) {
        if (numColuna === 1 && abaAtiva && (abaAtiva.ehPadrao === true || abaAtiva.titulo === "Geral")) {
            const p = document.createElement("p");
            p.className = "text-xs ui-text-muted text-center py-6 sem-conteudo-coluna";
            p.textContent = "Nenhuma seção criada nesta aba ainda.";
            conteinerSecoes.appendChild(p);
        } else {
            conteinerSecoes.innerHTML = `<p class="text-xs ui-text-muted text-center py-12 sem-conteudo-coluna">Nenhuma seção criada nesta aba ainda.</p>`;
        }
    } else {
        abaAtiva.secoes.forEach(secao => {
            const divSecao = document.createElement("div");
            divSecao.className = "p-5 ui-surface border ui-border rounded-2xl space-y-4 relative group/sec";

            const header = document.createElement("div");
            header.className = "flex items-center justify-between pb-2 border-b ui-border";

            const titulo = document.createElement("h4");
            titulo.className = "text-sm font-black ui-text-accent tracking-wide uppercase";
            titulo.textContent = secao.titulo;
            header.appendChild(titulo);

            const controle = document.createElement("div");
            controle.className = "flex items-center space-x-2";

            const tagTipo = document.createElement("span");
            tagTipo.className = "text-[9px] font-mono font-bold ui-component-soft px-2 py-0.5 rounded ui-text-muted";
            tagTipo.textContent = secao.tipo;
            controle.appendChild(tagTipo);

            if (estadoFicha.modo === "Edição") {
                const btnRem = document.createElement("button");
                btnRem.className = "p-1 ui-text-muted ui-hover-danger-text transition text-xs font-bold";
                btnRem.textContent = "EXCLUIR";
                btnRem.onclick = () => removerSecaoAba(numColuna, secao.id);
                controle.appendChild(btnRem);
            }
            header.appendChild(controle);
            divSecao.appendChild(header);

            const divCampos = document.createElement("div");
            if (secao.tipo === "AtributoSimples" || secao.tipo === "AtributoDuplo") {
                divCampos.className = "grid-atributos";
            } else {
                divCampos.className = "space-y-3";
            }
            if (!secao.componentes || secao.componentes.length === 0) {
                divCampos.innerHTML = `<p class="text-[10px] ui-text-muted text-center py-4">Nenhum elemento adicionado.</p>`;
            } else {
                secao.componentes.forEach(comp => {
                    divCampos.appendChild(renderizarComponenteFicha(numColuna, secao.id, comp, secao.tipo));
                });
            }
            divSecao.appendChild(divCampos);

            if (estadoFicha.modo === "Edição") {
                const btnAdd = document.createElement("button");
                btnAdd.className = "w-full py-2 ui-component-soft ui-hover-component ui-text-accent ui-hover-heading rounded-xl text-[10px] font-bold tracking-wider transition";
                btnAdd.textContent = "+ ADICIONAR ELEMENTO";
                btnAdd.onclick = () => adicionarComponenteSecao(numColuna, secao.id, secao.tipo);
                divSecao.appendChild(btnAdd);
            }

            conteinerSecoes.appendChild(divSecao);
        });
    }

    if (estadoFicha.modo === "Edição" && abaAtiva) {
        const btnAddSecao = document.createElement("button");
        btnAddSecao.className = "w-full py-4 border-2 border-dashed ui-border ui-hover-border-accent ui-hover-accent-soft rounded-2xl text-xs font-black tracking-wider ui-text-muted ui-hover-heading transition flex items-center justify-center space-x-2";
        btnAddSecao.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
 <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
 </svg>
 <span>ADICIONAR SEÇÃO</span>`;
        btnAddSecao.onclick = () => abrirModalNovaSecao(numColuna);
        conteinerSecoes.appendChild(btnAddSecao);
    }
}

function verificarOcultamentoColunasVazias() {
    const main = document.querySelector("main");
    let visiveis = 0;
    for (let c = 1; c <= 3; c++) {
        const colDiv = document.getElementById(`coluna_${c}`);
        const colObj = estadoFicha.colunas[c];
        const deveMostrar = estadoFicha.modo !== "Jogo" || (colObj && colObj.abas && colObj.abas.length > 0);
        if (colDiv) {
            if (deveMostrar) { colDiv.classList.remove("hidden"); visiveis++; }
            else { colDiv.classList.add("hidden"); }
        }
    }
    if (main) {
        main.classList.remove("lg:grid-cols-1", "lg:grid-cols-2", "lg:grid-cols-3");
        main.classList.add(`lg:grid-cols-${Math.max(visiveis, 1)}`);
    }
}
