// Bloco: edi??o do avatar e notifica??es do criador.

function mudarFoto() {
    if (!estadoFicha.podeEditar) {
        mostrarToastNotificacao("Acesso negado", "Você só pode visualizar esta ficha em modo jogo.", "erro");
        return;
    }
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';

    input.onchange = async function(e) {
        const arquivo = e.target.files[0];
        if (!arquivo) return;

        if (arquivo.size > 16 * 1024 * 1024) {
            mostrarToastNotificacao("Erro", "Arquivo muito grande. Máximo 16MB.", "erro");
            return;
        }

        const formatosPermitidos = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
        if (!formatosPermitidos.includes(arquivo.type)) {
            mostrarToastNotificacao("Erro", "Formato não suportado. Use PNG, JPG, GIF ou WEBP.", "erro");
            return;
        }

        mostrarToastNotificacao("Upload", "Enviando imagem...", "info");

        const formData = new FormData();
        formData.append('avatar', arquivo);

        try {
            const resposta = await fetch(`/api/ficha/${estadoFicha.id}/avatar`, {
                method: 'POST',
                headers: { 'X-CSRFToken': obterTokenCsrf() },
                body: formData
            });

            const dados = await resposta.json().catch(() => null);
            if (!resposta.ok) {
                throw new Error(dados?.erro || `Falha ao atualizar avatar (HTTP ${resposta.status}).`);
            }
            if (dados?.status === 'success') {
                const img = document.getElementById('avatar_imagem');
                const placeholder = document.getElementById('avatar_placeholder');
                if (img) {
                    img.src = dados.avatar_url + '?t=' + Date.now();
                    img.classList.remove('hidden');
                }
                if (placeholder) placeholder.classList.add('hidden');
                estadoFicha.avatar = dados.avatar_url;
                mostrarToastNotificacao("Sucesso", "Avatar atualizado!", "sucesso");
                agendarSalvamento();
            } else {
                throw new Error(dados?.erro || "Falha ao atualizar avatar.");
            }
        } catch (erro) {
            mostrarToastNotificacao("Erro", erro.message || "Falha ao fazer upload da imagem.", "erro");
        }
    };

    input.click();
}

function removerFoto() {
    if (!estadoFicha.podeEditar) {
        mostrarToastNotificacao("Acesso negado", "Você só pode visualizar esta ficha em modo jogo.", "erro");
        return;
    }
    const avatarImg = document.getElementById('avatar_imagem');
    const avatarPlaceholder = document.getElementById('avatar_placeholder');

    if (avatarImg) {
        avatarImg.classList.add('hidden');
        avatarImg.src = '';
    }
    if (avatarPlaceholder) {
        avatarPlaceholder.classList.remove('hidden');
    }

    if (estadoFicha) {
        estadoFicha.avatar = null;
        agendarSalvamento();
    }

    mostrarToastNotificacao("Avatar removido", "A imagem de perfil foi removida.", "alerta");
}

function mostrarToastNotificacao(titulo, texto, tipo) {
    let container = document.getElementById("painel_notificacoes");
    if (!container) {
        container = document.createElement('div');
        container.id = 'painel_notificacoes';
        container.className = 'fixed bottom-6 right-6 z-50 flex flex-col gap-3 max-w-sm w-full';
        container.style.pointerEvents = 'none';
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    let cor = "";
    if (tipo === "sucesso") {
        cor = "ui-border-positive ui-positive-soft";
    } else if (tipo === "erro") {
        cor = "ui-border-danger ui-danger-soft";
    } else if (tipo === "alerta") {
        cor = "ui-border-accent ui-accent-soft";
    } else {
        cor = "ui-border-accent ui-accent-soft";
    }

    toast.className = `toast-notificacao relative p-4 rounded-xl text-sm ${cor} text-white backdrop-blur-md shadow-2xl overflow-hidden`;
    toast.style.pointerEvents = 'auto';
    toast.style.animation = 'slideIn 0.3s ease-out forwards';

    toast.innerHTML = `
 <div class="absolute bottom-0 left-0 h-1 bg-gradient-to-r 
 ${tipo === 'sucesso' ? 'ui-gradient-positive' : 
 tipo === 'erro' ? 'ui-gradient-danger' : 
 tipo === 'alerta' ? 'ui-gradient-accent' : 
 'ui-gradient-accent'}"
 style="width: 100%; animation: progressBar 5s linear forwards;">
 </div>
 <div class="flex items-start space-x-3 relative z-10">
 <div class="flex-shrink-0 mt-0.5">
 ${tipo === 'sucesso' ? 
 `<svg class="w-5 h-5 ui-text-positive" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>` :
 tipo === 'erro' ?
 `<svg class="w-5 h-5 ui-text-danger" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
    </svg>` :
 tipo === 'alerta' ?
 `<svg class="w-5 h-5 ui-text-accent" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
    </svg>` :
 `<svg class="w-5 h-5 ui-text-accent" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12v-.008z" />
    </svg>`
 }
 </div>
 <div class="flex-1 min-w-0">
 <p class="text-sm font-bold text-white">${titulo}</p>
 <p class="text-xs ui-text-copy mt-0.5">${texto}</p>
 </div>
 <button onclick="fecharToast(this)" class="flex-shrink-0 ui-text-muted ui-hover-heading transition ml-2">
 <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
 <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
 </svg>
 </button>
 </div>
 `;

    container.appendChild(toast);

    setTimeout(() => {
        if (toast.parentNode) {
            toast.classList.add('fechando');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.remove();
                }
            }, 300);
        }
    }, 5000);
}

function fecharToast(button) {
    const toast = button.closest('.toast-notificacao');
    if (toast) {
        toast.classList.add('fechando');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 300);
    }
}
