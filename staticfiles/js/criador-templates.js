// Bloco: cria??o, aplica??o e remo??o de templates de ficha.

function abrirModalTemplate() {
    document.getElementById("modal_template").classList.remove("hidden");
    document.getElementById("nome_template_input").focus();
}

function fecharModalTemplate() {
    document.getElementById("modal_template").classList.add("hidden");
}

async function salvarComoTemplate() {
    const nome = document.getElementById("nome_template_input").value.trim();
    if (!nome) {
        mostrarToastNotificacao("Erro", "Informe um nome.", "erro");
        return;
    }
    try {
        const resp = await fetch(`/api/ficha/${estadoFicha.id}/template`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": obterTokenCsrf(),
            },
            body: JSON.stringify({ nome })
        });
        if (resp.ok) {
            mostrarToastNotificacao("Template salvo", `"${nome}" criado com sucesso!`, "sucesso");
            fecharModalTemplate();
        } else {
            const dados = await resp.json();
            mostrarToastNotificacao("Erro", dados.erro || "Não foi possível salvar.", "erro");
        }
    } catch {
        mostrarToastNotificacao("Erro", "Falha ao criar template.", "erro");
    }
}

async function abrirModalTemplateList() {
    const modal = document.getElementById("modal_template_list");
    const lista = document.getElementById("lista_templates_disponiveis");
    if (modal) modal.classList.remove("hidden");
    if (lista) lista.innerHTML = '<p class="text-sm ui-text-muted">Carregando templates...</p>';

    try {
        const dados = await enviarRequisicaoFicha(`/api/ficha/${estadoFicha.id}/template`);
        renderizarListaTemplates(dados.templates || []);
    } catch (erro) {
        if (lista) lista.innerHTML = '<p class="text-sm ui-text-muted">Falha ao carregar templates.</p>';
        mostrarToastNotificacao("Erro", "Não foi possível carregar os templates.", "erro");
    }
}

function fecharModalTemplateList() {
    const modal = document.getElementById("modal_template_list");
    if (modal) modal.classList.add("hidden");
}

function renderizarListaTemplates(templates) {
    const lista = document.getElementById("lista_templates_disponiveis");
    if (!lista) return;
    lista.innerHTML = "";

    if (!templates.length) {
        lista.innerHTML = '<p class="text-sm ui-text-muted">Nenhum template salvo ainda.</p>';
        return;
    }

    templates.forEach((template) => {
        const item = document.createElement("div");
        item.className = "border ui-border rounded-3xl p-4 grid gap-3 sm:grid-cols-[1fr_auto] items-start";
        item.style.backgroundColor = "#222234";
        item.innerHTML = `
 <div class="space-y-1">
 <p class="font-semibold text-white">${template.nomeTemplate}</p>
 <p class="text-xs ui-text-muted">Criado em ${template.dataCriacao || 'data desconhecida'}</p>
 </div>
 <div class="flex gap-2">
 <button type="button" class="px-4 py-2 rounded-xl ui-action ui-button-copy font-bold text-xs ui-hover-accent transition">Aplicar</button>
 <button type="button" class="px-4 py-2 rounded-xl ui-danger text-white font-bold text-xs ui-hover-danger transition">Excluir</button>
 </div>
 `;

        const botaoAplicar = item.querySelector("button:first-of-type");
        const botaoExcluir = item.querySelector("button:last-of-type");
        if (botaoAplicar) {
            botaoAplicar.addEventListener("click", () => aplicarTemplate(template.id, template.nomeTemplate));
        }
        if (botaoExcluir) {
            botaoExcluir.addEventListener("click", () => deletarTemplate(template.id, template.nomeTemplate));
        }
        lista.appendChild(item);
    });
}

async function deletarTemplate(templateId, nomeTemplate) {
    if (!confirm(`Excluir o template "${nomeTemplate}" não pode ser desfeito. Continuar?`)) {
        return;
    }

    try {
        await enviarRequisicaoFicha(`/api/ficha/${estadoFicha.id}/template/${templateId}`, {
            method: "DELETE"
        });

        mostrarToastNotificacao("Template excluído", `O template "${nomeTemplate}" foi removido.`, "sucesso");
        abrirModalTemplateList();
    } catch (erro) {
        mostrarToastNotificacao("Erro", "Falha ao excluir o template.", "erro");
    }
}

async function aplicarTemplate(templateId, nomeTemplate) {
    if (!confirm(`Aplicar o template "${nomeTemplate}" substituirá a estrutura atual da ficha. Continuar?`)) {
        return;
    }

    try {
        const dados = await enviarRequisicaoFicha(`/api/ficha/${estadoFicha.id}/template/${templateId}/apply`, {
            method: "POST"
        });

        estadoFicha = {
            ...estadoFicha,
            ...dados,
            modo: estadoFicha.modo,
            podeEditar: estadoFicha.podeEditar
        };

        normalizarIdsFicha();
        garantirAbaGeralPrimeiraColuna();
        garantirAbasAtivas();
        renderizarFichaCompleta();
        fecharModalTemplateList();
        mostrarToastNotificacao("Template aplicado", `O template "${nomeTemplate}" foi carregado.`, "sucesso");
    } catch (erro) {
        mostrarToastNotificacao("Erro", "Não foi possível aplicar o template.", "erro");
    }
}
