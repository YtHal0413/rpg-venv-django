// Bloco: inicialização do avatar e suporte aos diálogos personalizados.
document.addEventListener("DOMContentLoaded", function () {
    const avatarImg = document.getElementById("avatar_imagem");
    const avatarPlaceholder = document.getElementById("avatar_placeholder");

    if (estadoFicha && estadoFicha.avatar) {
        avatarImg.src = estadoFicha.avatar;
        avatarImg.classList.remove("hidden");
        if (avatarPlaceholder) avatarPlaceholder.classList.add("hidden");
    } else {
        avatarImg.classList.add("hidden");
        if (avatarPlaceholder) avatarPlaceholder.classList.remove("hidden");
    }
});

// Bloco: mantém a confirmação assíncrona usada pelas ações destrutivas.
let confirmacaoResolve = null;

function abrirModalConfirmacao(titulo, mensagem) {
    return new Promise((resolve) => {
        confirmacaoResolve = resolve;
        document.getElementById("confirmacao_titulo").textContent = titulo || "Tem certeza?";
        document.getElementById("confirmacao_mensagem").textContent =
        mensagem || "Esta ação não pode ser desfeita.";
        document.getElementById("modal_confirmacao").classList.remove("hidden");
    });
}

function fecharModalConfirmacao(resultado) {
    document.getElementById("modal_confirmacao").classList.add("hidden");
    if (!confirmacaoResolve) return;

    confirmacaoResolve(resultado);
    confirmacaoResolve = null;
}

// Bloco: coleta nomes por um diálogo reutilizável e acessível por teclado.
let promptResolve = null;

function abrirModalPrompt(titulo, mensagem, valorPadrao = "") {
    return new Promise((resolve) => {
        promptResolve = resolve;
        document.getElementById("prompt_titulo").textContent = titulo || "Digite o nome";
        document.getElementById("prompt_mensagem").textContent =
        mensagem || "Informe o título para continuar.";
        const input = document.getElementById("prompt_input");
        input.value = valorPadrao || "";
        input.focus();
        document.getElementById("modal_prompt").classList.remove("hidden");

        input.onkeydown = (event) => {
            if (event.key === "Enter") {
                fecharModalPrompt(input.value);
            }
        };
    });
}

function fecharModalPrompt(valor) {
    document.getElementById("modal_prompt").classList.add("hidden");
    if (!promptResolve) return;

    promptResolve(valor);
    promptResolve = null;
}

// Bloco: remove o avatar após confirmação e sincroniza o estado da ficha.
async function removerFoto() {
    const confirmado = await abrirModalConfirmacao(
    "Remover Avatar",
    "Tem certeza que deseja remover a foto de perfil?"
    );

    if (!confirmado) return;

    const avatarImg = document.getElementById("avatar_imagem");
    const avatarPlaceholder = document.getElementById("avatar_placeholder");

    if (avatarImg) {
        avatarImg.classList.add("hidden");
        avatarImg.src = "";
    }
    if (avatarPlaceholder) {
        avatarPlaceholder.classList.remove("hidden");
    }

    if (estadoFicha) {
        estadoFicha.avatar = null;
        agendarSalvamento();
    }

    mostrarToastNotificacao("Avatar removido", "A imagem de perfil foi removida.", "alerta");
}
