// Bloco: sincroniza presença, sessões, histórico e código de convite.
const campanhaPagina = document.getElementById("campanha-page");

if (campanhaPagina) {
    const presenceUrl = campanhaPagina.dataset.presenceUrl;
    const startSessionUrl = campanhaPagina.dataset.startSessionUrl;
    const stopSessionUrl = campanhaPagina.dataset.stopSessionUrl;
    const csrfToken = document.querySelector("#csrf-form [name='csrfmiddlewaretoken']").value;
    const sessionStatus = document.getElementById("status-sessao");
    const historyModal = document.getElementById("modal-historico-sessoes");
    const historyButton = document.getElementById("botao-historico-sessoes");

    function abrirHistoricoSessoes() {
        if (!historyModal) return;

        historyModal.classList.remove("hidden");
        historyModal.classList.add("flex");
        historyModal.setAttribute("aria-hidden", "false");
        document.getElementById("fechar-historico-sessoes").focus();
    }

    function fecharHistoricoSessoes() {
        if (!historyModal) return;

        historyModal.classList.add("hidden");
        historyModal.classList.remove("flex");
        historyModal.setAttribute("aria-hidden", "true");
        historyButton?.focus();
    }

    function abrirRelatorioSessao(sessaoId) {
        const container = document.getElementById("container-relatorio-sessoes");
        if (!container) return;
        container.querySelectorAll(".relatorio-sessao").forEach((item) => item.classList.add("hidden"));
        const relatorio = document.getElementById(`relatorio-sessao-${sessaoId}`);
        if (relatorio) relatorio.classList.remove("hidden");
        container.classList.remove("hidden");
    }

    function fecharRelatorioSessao() {
        const container = document.getElementById("container-relatorio-sessoes");
        if (container) container.classList.add("hidden");
    }

    function abrirChatbotCampanha() {
        const panel = document.getElementById("painel-chatbot-campanha");
        if (!panel) return;
        panel.classList.remove("hidden");
        document.getElementById("comando-chatbot-campanha")?.focus();
    }

    function fecharChatbotCampanha() {
        const panel = document.getElementById("painel-chatbot-campanha");
        if (!panel) return;
        panel.classList.add("hidden");
        document.getElementById("botao-chatbot-campanha")?.focus();
    }

    function escapeHtml(value) {
        const element = document.createElement("div");
        element.textContent = value;
        return element.innerHTML;
    }

    async function enviarComandoChatbot(event) {
        event.preventDefault();
        const input = document.getElementById("comando-chatbot-campanha");
        const messages = document.getElementById("chatbot-mensagens");
        const chatbotUrl = campanhaPagina.dataset.chatbotUrl;
        const comando = input?.value.trim();
        if (!comando || !chatbotUrl) return;

        input.disabled = true;
        const loading = document.createElement("p");
        loading.className = "rounded-2xl ui-component p-3 text-sm ui-text-muted";
        loading.textContent = "A IA está interpretando a cena...";
        messages.appendChild(loading);

        try {
            const response = await fetch(chatbotUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify({ comando }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.erro || "Não foi possível consultar o chatbot.");

            loading.remove();
            (data.mensagens || []).forEach((mensagem) => {
                const card = document.createElement("article");
                card.className = "rounded-2xl ui-component p-3";
                card.innerHTML = `<p class="text-xs font-black ui-text-accent">${escapeHtml(mensagem.personagem || "Personagem")}</p>`;
                const text = document.createElement("p");
                text.className = "mt-1 whitespace-pre-wrap text-sm ui-text-copy";
                text.textContent = mensagem.texto || "";
                card.appendChild(text);
                (mensagem.rolagens || []).forEach((rolagem) => {
                    const roll = document.createElement("p");
                    roll.className = "mt-2 rounded-lg ui-surface px-3 py-2 text-xs ui-text-positive";
                    roll.textContent = `${rolagem.teste || "Teste"}: d${rolagem.dados} · resultados [${(rolagem.resultados || []).join(", ")}]${rolagem.sucessos !== null && rolagem.sucessos !== undefined ? ` · sucessos ${rolagem.sucessos}` : ""}`;
                    card.appendChild(roll);
                });
                messages.appendChild(card);
            });
            input.value = "";
            messages.scrollTop = messages.scrollHeight;
        } catch (error) {
            loading.remove();
            const card = document.createElement("p");
            card.className = "rounded-2xl ui-danger-soft p-3 text-sm ui-text-danger";
            card.textContent = error.message;
            messages.appendChild(card);
        } finally {
            input.disabled = false;
            input.focus();
        }
    }

    window.abrirHistoricoSessoes = abrirHistoricoSessoes;
    window.fecharHistoricoSessoes = fecharHistoricoSessoes;
    window.abrirRelatorioSessao = abrirRelatorioSessao;
    window.fecharRelatorioSessao = fecharRelatorioSessao;
    window.abrirChatbotCampanha = abrirChatbotCampanha;
    window.fecharChatbotCampanha = fecharChatbotCampanha;

    // Bloco: fecha o histórico com Escape e mantém a navegação por teclado.
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && historyModal && !historyModal.classList.contains("hidden")) {
            fecharHistoricoSessoes();
        } else if (event.key === "Escape") {
            fecharChatbotCampanha();
        }
    });
    document.getElementById("form-chatbot-campanha")?.addEventListener("submit", enviarComandoChatbot);

    // Bloco: atualiza o indicador de presença dos participantes.
    async function updatePresence() {
        try {
            const response = await fetch(presenceUrl, {
                method: "POST",
                headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" },
            });
            if (!response.ok) throw new Error("Falha ao atualizar presença.");

            const data = await response.json();
            data.participantes.forEach((participant) => {
                const indicator = document.querySelector(`[data-presence-user="${participant.id}"]`);
                if (!indicator) return;

                indicator.textContent = `${participant.online ? "Online" : "Offline"} · ${indicator.textContent.split("·").slice(1).join("·").trim()}`;
                indicator.classList.toggle("ui-text-positive", participant.online);
                indicator.classList.toggle("ui-text-muted", !participant.online);
            });
        } catch (error) {
            if (sessionStatus) sessionStatus.textContent = error.message;
        }
    }

    // Bloco: inicia ou encerra uma sessão e apresenta falhas ao usuário.
    async function runSessionAction(url) {
        try {
            const response = await fetch(url, {
                method: "POST",
                headers: { "X-CSRFToken": csrfToken },
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.erro || "Não foi possível atualizar a sessão.");

            location.reload();
        } catch (error) {
            if (sessionStatus) sessionStatus.textContent = error.message;
        }
    }

    // Bloco: conecta os comandos de sessão e cópia do convite.
    document.getElementById("botao-iniciar-sessao")?.addEventListener("click", () => {
        runSessionAction(startSessionUrl);
    });
    document.getElementById("botao-parar-sessao")?.addEventListener("click", () => {
        if (confirm("Encerrar a sessão e salvar no histórico?")) {
            runSessionAction(stopSessionUrl);
        }
    });
    document.getElementById("copiar-codigo").addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(document.getElementById("codigo-convite").textContent.trim());
            document.getElementById("copiar-codigo").textContent = "Copiado!";
        } catch (error) {
            sessionStatus.textContent = "Não foi possível copiar o código. Selecione-o e copie manualmente.";
        }
    });

    // Bloco: exibe o tempo decorrido da sessão ativa.
    const timer = document.getElementById("timer-sessao");
    if (timer) {
        const startedAt = Date.parse(timer.dataset.iniciada);
        const updateTimer = () => {
            const total = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
            const hours = String(Math.floor(total / 3600)).padStart(2, "0");
            const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
            const seconds = String(total % 60).padStart(2, "0");
            timer.textContent = `${hours}:${minutes}:${seconds}`;
        };
        updateTimer();
        setInterval(updateTimer, 1000);
    }

    updatePresence();
    setInterval(updatePresence, 30000);
}
