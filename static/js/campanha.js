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
        historyModal.setAttribute("aria-hidden", "false");
        document.getElementById("fechar-historico-sessoes").focus();
    }

    function fecharHistoricoSessoes() {
        if (!historyModal) return;

        historyModal.classList.add("hidden");
        historyModal.setAttribute("aria-hidden", "true");
        historyButton?.focus();
    }

    window.abrirHistoricoSessoes = abrirHistoricoSessoes;
    window.fecharHistoricoSessoes = fecharHistoricoSessoes;

    // Bloco: fecha o histórico com Escape e mantém a navegação por teclado.
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && historyModal && !historyModal.classList.contains("hidden")) {
            fecharHistoricoSessoes();
        }
    });

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
