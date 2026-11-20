from functools import wraps
import json
import re
from datetime import timedelta
from pathlib import PurePath
from mimetypes import guess_type
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import (
    content_disposition_header,
    url_has_allowed_host_and_scheme,
)
from django.views.decorators.http import require_http_methods, require_POST

from .forms import (
    ArquivoUploadForm,
    CampanhaForm,
    CadastroForm,
    CodigoConviteForm,
    CriarFichaForm,
    LoginForm,
    PerfilForm,
    SenhaPerfilForm,
    CompraChaveForm,
    ResgateChaveForm,
)
from .fichas import (
    TIPOS_COMPONENTE,
    proximo_id_estrutura,
    renovar_ids_estrutura,
    validar_estrutura_ficha,
)
from .models import (
    Arquivo,
    Campanha,
    CampanhaParticipante,
    FichaCampanha,
    FichaPersonagem,
    SessaoCampanha,
    TemplateFicha,
    Usuario,
)
from .campanhas import (
    LimiteCampanhaAtingido,
    criar_campanha,
    entrar_em_campanha,
    iniciar_sessao,
    parar_sessao,
    remover_participante,
    sair_da_campanha,
)
from .services import (
    ChaveIndisponivel,
    comprar_chave,
    pode_criar_campanha,
    pode_criar_ficha,
    pode_participar_campanha,
    resgatar_chave,
    tem_acesso_ilimitado,
)
from .chatbot import (
    GeminiIndisponivel,
    enviar_comando,
    gerar_relatorio,
    personagens_faltosos,
)


def _safe_next_url(request, next_url):
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse("perfil")


def _redirect_to_store(request):
    destination = _safe_next_url(request, request.POST.get("next"))
    parts = urlsplit(destination)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["loja"] = "1"
    if parts.path == reverse("perfil"):
        query["aba"] = "chaves"
    return redirect(urlunsplit(parts._replace(query=urlencode(query))))


def inicio(request):
    return render(request, "inicio.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("perfil")

    next_url = request.POST.get("next") or request.GET.get("next", "")
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        messages.success(request, "Login realizado com sucesso.")
        return redirect(_safe_next_url(request, next_url))

    return render(
        request,
        "login.html",
        {
            "form": form,
            "modo": "login",
            "next_url": next_url,
        },
    )


def cadastro_view(request):
    if request.user.is_authenticated:
        return redirect("perfil")

    next_url = request.POST.get("next") or request.GET.get("next", "")
    form = CadastroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Conta criada com sucesso.")
        return redirect(_safe_next_url(request, next_url))

    return render(
        request,
        "login.html",
        {
            "form": form,
            "modo": "cadastro",
            "next_url": next_url,
        },
    )


@login_required
def perfil(request):
    perfil_form = PerfilForm(instance=request.user)
    senha_form = SenhaPerfilForm(request.user)
    active_tab = request.GET.get("aba", "construcao")
    if active_tab not in {"construcao", "editar", "chaves"}:
        active_tab = "construcao"

    if request.method == "POST":
        active_tab = "editar"
        if request.POST.get("acao") == "senha":
            senha_form = SenhaPerfilForm(request.user, request.POST)
            if senha_form.is_valid():
                senha_form.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, "Senha atualizada com sucesso.")
                return redirect("perfil")
        else:
            perfil_form = PerfilForm(
                request.POST,
                request.FILES,
                instance=request.user,
            )
            if perfil_form.is_valid():
                old_avatar = request.user.avatar
                old_avatar_name = old_avatar.name
                user = perfil_form.save()
                if old_avatar_name and old_avatar_name != user.avatar.name:
                    old_avatar.close()
                    old_avatar.storage.delete(old_avatar_name)
                messages.success(request, "Perfil atualizado com sucesso.")
                return redirect("perfil")

    return render(
        request,
        "perfil.html",
        {
            "perfil_form": perfil_form,
            "senha_form": senha_form,
            "usuario": request.user,
            "active_tab": active_tab,
            "chaves": request.user.chaves.all(),
        },
    )


@login_required
def colecoes(request):
    fichas = _fichas_resumo(request.user)
    campanhas = Campanha.objects.filter(
        vinculos_participantes__usuario=request.user
    ).select_related("mestre").distinct()
    return render(
        request,
        "colecoes.html",
        {
            "tem_acesso_ilimitado": tem_acesso_ilimitado(request.user),
            "fichas": fichas,
            "campanhas": campanhas,
        },
    )


def _fichas_resumo(usuario):
    return [
        {
            "id": ficha.pk,
            "nome_personagem": ficha.nome,
            "avatar": reverse("avatar_ficha", args=[ficha.pk])
            if ficha.avatar
            else None,
        }
        for ficha in FichaPersonagem.objects.filter(usuario=usuario)
    ]


@login_required
def personagens(request):
    fichas = _fichas_resumo(request.user)
    limite_atingido = not pode_criar_ficha(request.user, len(fichas))
    return render(
        request,
        "gerenciar_fichas.html",
        {
            "fichas": fichas,
            "limite_atingido": limite_atingido,
        },
    )


@login_required
@require_POST
def criar_ficha_view(request):
    form = CriarFichaForm(request.POST)
    if not form.is_valid():
        mensagens = [
            str(erro)
            for campo in form.errors.values()
            for erro in campo
        ]
        messages.error(
            request,
            " ".join(mensagens) or "Informe o nome e o aspecto do personagem.",
        )
        return redirect("personagens")

    with transaction.atomic():
        usuario = Usuario.objects.select_for_update().get(pk=request.user.pk)
        fichas_ativas = FichaPersonagem.objects.filter(usuario=request.user).count()
        if not pode_criar_ficha(usuario, fichas_ativas):
            messages.error(
                request,
                "Sua conta básica pode manter apenas uma ficha ativa. "
                "Exclua a ficha atual ou ative o acesso ilimitado.",
            )
            return redirect("personagens")
        ficha = FichaPersonagem.objects.create(
            usuario=request.user,
            nome=form.cleaned_data["nome_personagem"],
            aspecto=form.cleaned_data["subtitulo"],
        )

    estrutura = ficha.estrutura_json
    estrutura["id"] = ficha.pk
    estrutura["nome"] = ficha.nome
    estrutura["subtitulo"] = ficha.aspecto
    ficha.estrutura_json = estrutura
    ficha.save(update_fields=["estrutura_json", "atualizada_em"])
    messages.success(request, f"Personagem '{ficha.nome}' criado com sucesso.")
    return redirect("criador", ficha_id=ficha.pk)


@login_required
@require_POST
def excluir_ficha_view(request, ficha_id):
    ficha = get_object_or_404(
        FichaPersonagem.objects.filter(usuario=request.user),
        pk=ficha_id,
    )
    if ficha.avatar:
        ficha.avatar.storage.delete(ficha.avatar.name)
    ficha.delete()
    messages.success(request, "Personagem excluído.")
    return redirect("personagens")


@login_required
def criador_ficha(request, ficha_id):
    ficha = FichaPersonagem.objects.filter(
        usuario=request.user,
        pk=ficha_id,
    ).first()
    pode_editar = ficha is not None
    if ficha is None:
        ficha = get_object_or_404(FichaPersonagem, pk=ficha_id)
        campanha_id = request.GET.get("campanha")
        if not _usuario_pode_visualizar_ficha(
            request.user,
            ficha,
            campanha_id=campanha_id,
        ):
            raise Http404("Ficha não disponível para este usuário.")
    ficha.visibilidade = ficha.estrutura_json.get("visibilidade", "todos")
    return render(
        request,
        "ficha.html",
        {
            "ficha": ficha,
            "pode_editar": pode_editar,
            "modo_inicial": "Jogo",
        },
    )


def _usuario_pode_visualizar_ficha(usuario, ficha, campanha_id=None):
    if ficha.usuario_id == usuario.pk:
        return True
    visibilidade = ficha.estrutura_json.get("visibilidade", "todos")
    if campanha_id is not None:
        try:
            campanha_id = int(campanha_id)
        except (TypeError, ValueError):
            return False
    campanhas = Campanha.objects.filter(
        vinculos_participantes__usuario=usuario,
        vinculos_fichas__ficha=ficha,
    )
    if campanha_id:
        campanhas = campanhas.filter(pk=campanha_id)
    if visibilidade == "mestres":
        campanhas = campanhas.filter(mestre=usuario)
    return campanhas.exists()


def _api_erro(mensagem, status=400):
    return JsonResponse({"erro": mensagem}, status=status)


def api_login_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _api_erro("Autentique-se para acessar este recurso.", 401)
        try:
            return view(request, *args, **kwargs)
        except Http404:
            return _api_erro("O recurso solicitado não foi encontrado.", 404)

    return wrapped


def _obter_ficha_propria(usuario, ficha_id):
    return get_object_or_404(
        FichaPersonagem.objects.filter(usuario=usuario),
        pk=ficha_id,
    )


def _dados_ficha(ficha):
    estrutura = ficha.estrutura_json
    return {
        "id": ficha.pk,
        "nome": ficha.nome,
        "subtitulo": ficha.aspecto,
        "avatar": reverse("avatar_ficha", args=[ficha.pk]) if ficha.avatar else None,
        "visibilidade": estrutura.get("visibilidade", "todos"),
        "colunas": estrutura.get("colunas", {}),
    }


def _ler_json_api(request, limite=1_000_000):
    try:
        if int(request.headers.get("Content-Length", "0")) > limite:
            return None, "A requisição excede o tamanho permitido."
        dados = json.loads(request.body)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "Envie um objeto JSON válido."
    if not isinstance(dados, dict):
        return None, "O corpo da requisição deve ser um objeto JSON."
    return dados, None


def _salvar_estado_ficha(ficha, dados):
    nome = dados.get("nome")
    aspecto = dados.get("subtitulo", "")
    if not isinstance(nome, str) or not nome.strip() or len(nome) > 100:
        raise ValidationError("O nome do personagem é obrigatório e deve ter até 100 caracteres.")
    if not isinstance(aspecto, str) or len(aspecto) > 240:
        raise ValidationError("O aspecto deve ter até 240 caracteres.")
    estrutura = validar_estrutura_ficha(dados)
    ficha.nome = nome.strip()
    ficha.aspecto = aspecto.strip()
    ficha.estrutura_json = estrutura
    avatar_antigo = None
    if "avatar" in dados and dados["avatar"] is None and ficha.avatar:
        avatar_antigo = ficha.avatar.name
        ficha.avatar = None
    ficha.save(
        update_fields=[
            "nome",
            "aspecto",
            "estrutura_json",
            "avatar",
            "atualizada_em",
        ]
    )
    if avatar_antigo:
        ficha.avatar.storage.delete(avatar_antigo)


@api_login_required
@require_http_methods(["GET", "POST"])
def api_ficha(request, ficha_id):
    if request.method == "GET":
        ficha = FichaPersonagem.objects.filter(pk=ficha_id).first()
        if ficha is None or not _usuario_pode_visualizar_ficha(
            request.user,
            ficha,
            campanha_id=request.GET.get("campanha"),
        ):
            raise Http404
        return JsonResponse(_dados_ficha(ficha))
    ficha = _obter_ficha_propria(request.user, ficha_id)
    dados, erro = _ler_json_api(request)
    if erro:
        return _api_erro(erro)
    try:
        with transaction.atomic():
            ficha = FichaPersonagem.objects.select_for_update().get(
                pk=ficha_id,
                usuario=request.user,
            )
            _salvar_estado_ficha(ficha, dados)
    except ValidationError as error:
        return _api_erro("; ".join(error.messages))
    return JsonResponse({"status": "success"})


@api_login_required
@require_http_methods(["GET", "POST"])
def api_templates_ficha(request, ficha_id):
    ficha = _obter_ficha_propria(request.user, ficha_id)
    if request.method == "GET":
        return JsonResponse(
            {
                "templates": [
                    {
                        "id": item.pk,
                        "nomeTemplate": item.nome,
                        "dataCriacao": item.criado_em.strftime("%d/%m/%Y %H:%M"),
                    }
                    for item in TemplateFicha.objects.filter(usuario=request.user)
                ]
            }
        )

    dados, erro = _ler_json_api(request, limite=4000)
    if erro:
        return _api_erro(erro)
    nome = dados.get("nome")
    if not isinstance(nome, str) or not nome.strip() or len(nome.strip()) > 100:
        return _api_erro("Informe um nome de template com até 100 caracteres.")
    template = TemplateFicha.objects.create(
        usuario=request.user,
        ficha_origem=ficha,
        nome=nome.strip(),
        estrutura_json=ficha.estrutura_json,
    )
    return JsonResponse(
        {"status": "success", "id": template.pk, "nome": template.nome},
        status=201,
    )


@api_login_required
@require_POST
def api_aplicar_template_ficha(request, ficha_id, template_id):
    ficha = _obter_ficha_propria(request.user, ficha_id)
    template = get_object_or_404(
        TemplateFicha.objects.filter(usuario=request.user),
        pk=template_id,
    )
    estrutura = renovar_ids_estrutura(template.estrutura_json)
    estrutura["visibilidade"] = ficha.estrutura_json.get("visibilidade", "todos")
    ficha.estrutura_json = validar_estrutura_ficha(estrutura)
    ficha.save(update_fields=["estrutura_json", "atualizada_em"])
    return JsonResponse(_dados_ficha(ficha))


@api_login_required
@require_http_methods(["DELETE"])
def api_excluir_template_ficha(request, ficha_id, template_id):
    _obter_ficha_propria(request.user, ficha_id)
    template = get_object_or_404(
        TemplateFicha.objects.filter(usuario=request.user),
        pk=template_id,
    )
    template.delete()
    return JsonResponse({"status": "success"})


@api_login_required
@require_POST
def api_avatar_ficha(request, ficha_id):
    ficha = _obter_ficha_propria(request.user, ficha_id)
    arquivo = request.FILES.get("avatar")
    if not arquivo:
        return _api_erro("Selecione uma imagem para o avatar.")
    if arquivo.size > 16 * 1024 * 1024:
        return _api_erro("O avatar deve ter no máximo 16 MiB.")
    try:
        ficha.avatar.field.clean(arquivo, ficha)
    except ValidationError as error:
        return _api_erro("; ".join(error.messages))
    antigo = ficha.avatar.name if ficha.avatar else None
    ficha.avatar = arquivo
    ficha.save(update_fields=["avatar", "atualizada_em"])
    if antigo:
        ficha.avatar.storage.delete(antigo)
    return JsonResponse(
        {
            "status": "success",
            "avatar_url": reverse("avatar_ficha", args=[ficha.pk]),
            "message": "Avatar atualizado.",
        }
    )


@login_required
def avatar_ficha(request, ficha_id):
    ficha = get_object_or_404(FichaPersonagem, pk=ficha_id)
    if not _usuario_pode_visualizar_ficha(request.user, ficha):
        raise Http404("Avatar não encontrado.")
    if not ficha.avatar:
        raise Http404("Avatar não encontrado.")
    content_type = guess_type(ficha.avatar.name)[0] or "application/octet-stream"
    response = FileResponse(
        ficha.avatar.open("rb"),
        as_attachment=False,
        filename=PurePath(ficha.avatar.name).name,
        content_type=content_type,
    )
    response["Cache-Control"] = "private, no-store"
    return response


def _salvar_mutacao_ficha(ficha, estrutura):
    try:
        ficha.estrutura_json = validar_estrutura_ficha(estrutura)
    except ValidationError as error:
        return _api_erro("; ".join(error.messages))
    ficha.save(update_fields=["estrutura_json", "atualizada_em"])
    return None


def _secao_por_id(estrutura, secao_id):
    for coluna in estrutura.get("colunas", {}).values():
        for aba in coluna.get("abas", []):
            for secao in aba.get("secoes", []):
                if secao.get("id") == secao_id:
                    return aba, secao
    return None, None


def _componente_por_id(estrutura, componente_id):
    for coluna in estrutura.get("colunas", {}).values():
        for aba in coluna.get("abas", []):
            for secao in aba.get("secoes", []):
                for componente in secao.get("componentes", []):
                    if componente.get("id") == componente_id:
                        return secao, componente
    return None, None


def _componente_padrao(tipo, componente_id):
    comuns = {"id": componente_id}
    padroes = {
        "AtributoSimples": {"nomeAtributo": "", "valorAtributo": 0},
        "AtributoDuplo": {
            "nomeAtributo": "",
            "valorGrande": 0,
            "valorPequeno": 0,
        },
        "AtributoComplexo": {
            "nomeAtributo": "",
            "valorBase": 0,
            "valorBonus": 0,
            "valorOutros": 0,
            "subtituloAnotacao": "",
            "criterioOrdenacao": 0,
        },
        "Contador": {
            "rotulo": "",
            "valorAtual": 0,
            "valorMaximo": 10,
            "corSeletor": "#4A4E69",
        },
        "Checkbox": {"rotulo": "", "estaMarcado": False},
        "InformacaoCurta": {"rotulo": "", "campoTexto": ""},
        "AnotacaoSimples": {"rotulo": "", "descricao": ""},
        "AnotacaoCheckbox": {
            "rotulo": "",
            "descricao": "",
            "estaMarcado": False,
        },
        "AnotacaoDetalhada": {
            "rotulo": "",
            "descricao": "",
            "anotacaoExtra": "",
        },
    }
    return {**comuns, **padroes[tipo]}


@api_login_required
@require_POST
def api_criar_aba_ficha(request, ficha_id):
    ficha = _obter_ficha_propria(request.user, ficha_id)
    dados, erro = _ler_json_api(request, limite=4000)
    if erro:
        return _api_erro(erro)
    numero = dados.get("posicaoColuna")
    if numero not in (1, 2, 3):
        return _api_erro("Selecione uma coluna válida.")
    estrutura = ficha.estrutura_json
    coluna = estrutura["colunas"].get(str(numero))
    if coluna is None:
        return _api_erro("Coluna não encontrada.", 404)
    if len(coluna["abas"]) >= 3:
        return _api_erro("Cada coluna pode conter no máximo três abas.")
    titulo = dados.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip() or len(titulo.strip()) > 80:
        return _api_erro("Informe um título de aba com até 80 caracteres.")
    aba_id = proximo_id_estrutura(estrutura)
    aba = {
        "id": aba_id,
        "titulo": titulo.strip(),
        "ehPadrao": False,
        "secoes": [],
    }
    coluna["abas"].append(aba)
    coluna["abaAtivaId"] = aba_id
    erro = _salvar_mutacao_ficha(ficha, estrutura)
    if erro:
        return erro
    return JsonResponse({"status": "success", "aba": {"id": aba_id, "titulo": aba["titulo"]}})


@api_login_required
@require_http_methods(["DELETE"])
def api_excluir_aba_ficha(request, ficha_id, aba_id):
    ficha = _obter_ficha_propria(request.user, ficha_id)
    estrutura = ficha.estrutura_json
    for coluna_numero, coluna in estrutura["colunas"].items():
        aba = next((item for item in coluna["abas"] if item.get("id") == aba_id), None)
        if aba is None:
            continue
        if coluna_numero == "1" and (
            aba.get("ehPadrao") or aba.get("titulo") == "Geral"
        ):
            return _api_erro("A primeira aba da primeira coluna não pode ser removida.")
        coluna["abas"].remove(aba)
        if coluna.get("abaAtivaId") == aba_id:
            coluna["abaAtivaId"] = coluna["abas"][0]["id"] if coluna["abas"] else None
        erro = _salvar_mutacao_ficha(ficha, estrutura)
        return erro or JsonResponse({"status": "success"})
    return _api_erro("Aba não encontrada.", 404)


@api_login_required
@require_POST
def api_criar_secao_ficha(request, ficha_id):
    ficha = _obter_ficha_propria(request.user, ficha_id)
    dados, erro = _ler_json_api(request, limite=4000)
    if erro:
        return _api_erro(erro)
    tipo = dados.get("tipo", "AtributoSimples")
    if tipo not in TIPOS_COMPONENTE:
        return _api_erro("Selecione um tipo de seção válido.")
    titulo = dados.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip() or len(titulo.strip()) > 100:
        return _api_erro("Informe um título de seção com até 100 caracteres.")
    estrutura = ficha.estrutura_json
    aba = next(
        (
            item
            for coluna in estrutura["colunas"].values()
            for item in coluna["abas"]
            if item.get("id") == dados.get("abaId")
        ),
        None,
    )
    if aba is None:
        return _api_erro("Aba não encontrada.", 404)
    secao = {
        "id": proximo_id_estrutura(estrutura),
        "titulo": titulo.strip(),
        "tipo": tipo,
        "componentes": [],
    }
    aba["secoes"].append(secao)
    erro = _salvar_mutacao_ficha(ficha, estrutura)
    if erro:
        return erro
    return JsonResponse({"status": "success", "secao": {"id": secao["id"], "titulo": secao["titulo"]}})


@api_login_required
@require_http_methods(["DELETE"])
def api_excluir_secao_ficha(request, ficha_id, secao_id):
    ficha = _obter_ficha_propria(request.user, ficha_id)
    estrutura = ficha.estrutura_json
    for coluna in estrutura["colunas"].values():
        for aba in coluna["abas"]:
            secao = next(
                (item for item in aba["secoes"] if item.get("id") == secao_id),
                None,
            )
            if secao is not None:
                aba["secoes"].remove(secao)
                erro = _salvar_mutacao_ficha(ficha, estrutura)
                return erro or JsonResponse({"status": "success"})
    return _api_erro("Seção não encontrada.", 404)


@api_login_required
@require_POST
def api_criar_componente_ficha(request, ficha_id):
    ficha = _obter_ficha_propria(request.user, ficha_id)
    dados, erro = _ler_json_api(request, limite=4000)
    if erro:
        return _api_erro(erro)
    tipo = dados.get("tipo")
    if tipo not in TIPOS_COMPONENTE:
        return _api_erro("Selecione um tipo de componente válido.")
    estrutura = ficha.estrutura_json
    _, secao = _secao_por_id(estrutura, dados.get("secaoId"))
    if secao is None:
        return _api_erro("Seção não encontrada.", 404)
    if secao["tipo"] != tipo:
        return _api_erro("O tipo de componente não corresponde à seção.")
    componente = _componente_padrao(tipo, proximo_id_estrutura(estrutura))
    secao["componentes"].append(componente)
    erro = _salvar_mutacao_ficha(ficha, estrutura)
    if erro:
        return erro
    return JsonResponse({"status": "success", "componente": componente})


@api_login_required
@require_http_methods(["PUT", "DELETE"])
def api_atualizar_componente_ficha(request, ficha_id, componente_id):
    ficha = _obter_ficha_propria(request.user, ficha_id)
    if request.method == "DELETE":
        estrutura = ficha.estrutura_json
        for coluna in estrutura["colunas"].values():
            for aba in coluna["abas"]:
                for secao in aba["secoes"]:
                    componente = next(
                        (
                            item
                            for item in secao["componentes"]
                            if item.get("id") == componente_id
                        ),
                        None,
                    )
                    if componente is not None:
                        secao["componentes"].remove(componente)
                        erro = _salvar_mutacao_ficha(ficha, estrutura)
                        return erro or JsonResponse({"status": "success"})
        return _api_erro("Componente não encontrado.", 404)

    dados, erro = _ler_json_api(request, limite=4000)
    if erro:
        return _api_erro(erro)
    estrutura = ficha.estrutura_json
    secao, componente = _componente_por_id(estrutura, componente_id)
    if componente is None:
        return _api_erro("Componente não encontrado.", 404)
    campos_por_tipo = {
        "AtributoSimples": {"nomeAtributo", "valorAtributo"},
        "AtributoDuplo": {"nomeAtributo", "valorGrande", "valorPequeno"},
        "AtributoComplexo": {
            "nomeAtributo", "valorBase", "valorBonus", "valorOutros",
            "subtituloAnotacao", "criterioOrdenacao",
        },
        "Contador": {"rotulo", "valorAtual", "valorMaximo", "corSeletor"},
        "Checkbox": {"rotulo", "estaMarcado"},
        "InformacaoCurta": {"rotulo", "campoTexto"},
        "AnotacaoSimples": {"rotulo", "descricao"},
        "AnotacaoCheckbox": {"rotulo", "descricao", "estaMarcado"},
        "AnotacaoDetalhada": {"rotulo", "descricao", "anotacaoExtra"},
    }
    if not dados or not set(dados).issubset(campos_por_tipo[secao["tipo"]]):
        return _api_erro("Os campos enviados não são válidos para este componente.")
    componente.update(dados)
    erro = _salvar_mutacao_ficha(ficha, estrutura)
    return erro or JsonResponse({"status": "success", "componente": componente})


@login_required
@require_POST
def comprar_chave_view(request):
    form = CompraChaveForm(request.POST)
    if not form.is_valid():
        messages.error(request, "O pacote selecionado não está disponível.")
        return _redirect_to_store(request)

    comprar_chave(request.user)
    messages.success(
        request,
        "A chave foi enviada para o seu perfil.",
    )
    return _redirect_to_store(request)


@login_required
@require_POST
def resgatar_chave_view(request):
    form = ResgateChaveForm(request.POST)
    if not form.is_valid():
        erros = [str(erro) for campo in form.errors.values() for erro in campo]
        messages.error(request, " ".join(erros) or "Informe uma chave.")
        return _redirect_to_store(request)

    try:
        resgatar_chave(request.user, form.cleaned_data["codigo"])
    except ChaveIndisponivel as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            "Chave resgatada. O acesso ilimitado foi ativado para sua conta.",
        )
    return _redirect_to_store(request)


@login_required
def biblioteca(request):
    arquivos = Arquivo.objects.filter(usuario=request.user)
    form = ArquivoUploadForm()

    if request.method == "POST":
        form = ArquivoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo = form.save(commit=False)
            arquivo.usuario = request.user
            arquivo.nome_original = PurePath(
                request.FILES["arquivo"].name.replace("\\", "/")
            ).name[:255]
            arquivo.save()
            messages.success(request, "Arquivo enviado para sua biblioteca.")
            return redirect("livros")

        messages.error(request, "Não foi possível enviar o arquivo. Verifique o formato ou tamanho.")

    return render(
        request,
        "livros.html",
        {
            "arquivos": arquivos,
            "form": form,
            "max_upload_size": 16 * 1024 * 1024,
        },
    )


@login_required
def visualizar_arquivo(request, arquivo_id):
    """Serve arquivos autorizados e suporta requisições parciais para PDFs."""
    arquivo = Arquivo.objects.filter(
        pk=arquivo_id,
        usuario=request.user,
    ).first()
    if arquivo is None:
        arquivo = get_object_or_404(
            Arquivo.objects.filter(
                campanhas__vinculos_participantes__usuario=request.user
            ).distinct(),
            pk=arquivo_id,
        )
    if not arquivo.arquivo:
        raise Http404("O arquivo não está disponível.")
    if arquivo.tipo not in {Arquivo.Tipo.DOCUMENTO, Arquivo.Tipo.HANDOUT}:
        raise Http404("O arquivo não está disponível.")

    content_types = {
        "documento": "application/pdf",
        "handout": (
            "image/png"
            if arquivo.arquivo.name.lower().endswith(".png")
            else "image/jpeg"
        ),
    }
    file_size = arquivo.arquivo.size
    content_type = content_types[arquivo.tipo]
    range_header = request.headers.get("Range")

    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match or file_size == 0:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{file_size}"
            return response

        range_start, range_end = match.groups()
        if range_start:
            start = int(range_start)
            end = min(int(range_end), file_size - 1) if range_end else file_size - 1
        elif range_end:
            suffix_length = int(range_end)
            if suffix_length == 0:
                start = file_size
                end = file_size - 1
            else:
                start = max(file_size - suffix_length, 0)
                end = file_size - 1
        else:
            start = file_size
            end = file_size - 1

        if start >= file_size or start > end:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{file_size}"
            return response

        length = end - start + 1
        file_handle = arquivo.arquivo.open("rb")
        file_handle.seek(start)

        def stream_range():
            remaining = length
            try:
                while remaining:
                    chunk = file_handle.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
            finally:
                file_handle.close()

        response = StreamingHttpResponse(
            stream_range(),
            status=206,
            content_type=content_type,
        )
        response["Content-Length"] = str(length)
        response["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        response["Content-Disposition"] = content_disposition_header(
            False,
            arquivo.nome_original,
        )
    else:
        response = FileResponse(
            arquivo.arquivo.open("rb"),
            as_attachment=False,
            filename=arquivo.nome_original,
            content_type=content_type,
        )
        response["Content-Length"] = str(file_size)

    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_POST
def remover_arquivo(request, arquivo_id):
    arquivo = get_object_or_404(
        Arquivo.objects.filter(usuario=request.user),
        pk=arquivo_id,
    )
    if arquivo.arquivo:
        stored_file = arquivo.arquivo
        stored_file_name = stored_file.name
        stored_file.close()
        stored_file.storage.delete(stored_file_name)
    arquivo.delete()
    messages.success(request, "Arquivo removido da sua biblioteca.")
    return redirect("livros")


@login_required
def avatar_proprio(request):
    avatar = request.user.avatar
    if not avatar:
        raise Http404("Avatar não encontrado.")
    content_type = guess_type(avatar.name)[0] or "application/octet-stream"
    response = FileResponse(
        avatar.open("rb"),
        as_attachment=False,
        filename=PurePath(avatar.name).name,
        content_type=content_type,
    )
    response["Cache-Control"] = "private, no-store"
    return response


def _campanha_propria(request, campanha_id):
    return get_object_or_404(
        Campanha.objects.filter(vinculos_participantes__usuario=request.user)
        .select_related("mestre")
        .distinct(),
        pk=campanha_id,
    )


def _campanha_do_mestre(request, campanha_id):
    return get_object_or_404(
        Campanha.objects.filter(mestre=request.user),
        pk=campanha_id,
    )


def _redirecionar_campanha(campanha):
    return redirect("campanha", campanha_id=campanha.pk)


@login_required
def gerenciar_campanhas(request):
    return render(
        request,
        "gerenciar_campanha.html",
        _contexto_gerenciar_campanhas(request.user),
    )


def _contexto_gerenciar_campanhas(usuario, form_campanha=None, abrir_modal=False):
    campanhas = Campanha.objects.filter(
        vinculos_participantes__usuario=usuario
    ).select_related("mestre").distinct()
    participacao_ativa = CampanhaParticipante.objects.filter(
        usuario=usuario
    ).count()
    return {
        "campanhas": campanhas,
        "pode_criar_campanha": pode_criar_campanha(usuario),
        "limite_participacao_atingido": not pode_participar_campanha(
            usuario,
            participacao_ativa,
        ),
        "form_convite": CodigoConviteForm(),
        "form_campanha": (
            form_campanha if form_campanha is not None else CampanhaForm()
        ),
        "abrir_modal_criacao": abrir_modal,
    }


@login_required
@require_http_methods(["GET", "POST"])
def criar_campanha_view(request):
    if request.method == "GET":
        return redirect("campanhas")

    if not pode_criar_campanha(request.user):
        messages.error(
            request,
            "A criação de campanhas exige acesso ilimitado. Ative uma chave para continuar.",
        )
        return redirect("campanhas")

    form = CampanhaForm(request.POST)
    if request.method == "POST" and form.is_valid():
        try:
            campanha = criar_campanha(
                request.user,
                form.cleaned_data["titulo"],
                form.cleaned_data["descricao"],
            )
        except ValidationError as error:
            for mensagem in error.messages:
                form.add_error(None, mensagem)
        else:
            messages.success(request, "Campanha criada com sucesso.")
            return _redirecionar_campanha(campanha)

    return render(
        request,
        "gerenciar_campanha.html",
        _contexto_gerenciar_campanhas(request.user, form, abrir_modal=True),
    )


@login_required
@require_POST
def entrar_campanha_view(request):
    form = CodigoConviteForm(request.POST)
    if not form.is_valid():
        messages.error(
            request,
            " ".join(
                str(erro)
                for erros in form.errors.values()
                for erro in erros
            )
            or "Informe um código de convite válido.",
        )
        return redirect("campanhas")
    try:
        campanha, entrou = entrar_em_campanha(
            request.user,
            form.cleaned_data["codigo_campanha"],
        )
    except Campanha.DoesNotExist:
        messages.error(request, "Campanha não encontrada para este código.")
        return redirect("campanhas")
    except LimiteCampanhaAtingido as error:
        messages.error(request, str(error))
        return redirect("campanhas")
    messages.success(
        request,
        f"Você {'entrou na' if entrou else 'já participa da'} campanha “{campanha.titulo}”.",
    )
    return _redirecionar_campanha(campanha)


@login_required
@require_http_methods(["GET", "POST"])
def campanha_detalhes(request, campanha_id):
    """Render campaign data with participant sheets loaded in a single query."""
    campanha = _campanha_propria(request, campanha_id)
    eh_mestre = campanha.mestre_id == request.user.pk
    vinculo = CampanhaParticipante.objects.get(
        campanha=campanha,
        usuario=request.user,
    )
    vinculo.ultimo_acesso = timezone.now()
    vinculo.save(update_fields=["ultimo_acesso"])

    if request.method == "POST":
        if not eh_mestre:
            messages.error(request, "Somente o mestre pode editar a campanha.")
            return _redirecionar_campanha(campanha)
        form = CampanhaForm(request.POST)
        if form.is_valid():
            campanha.titulo = form.cleaned_data["titulo"]
            campanha.descricao = form.cleaned_data["descricao"]
            campanha.save(update_fields=["titulo", "descricao", "atualizada_em"])
            messages.success(request, "Dados da campanha atualizados.")
        else:
            messages.error(request, "Informe um título válido para a campanha.")
        return _redirecionar_campanha(campanha)

    agora = timezone.now()
    participantes = []
    fichas_vinculadas = list(
        FichaPersonagem.objects.filter(
            vinculos_campanhas__campanha=campanha
        ).select_related("usuario").distinct()
    )
    fichas_por_usuario = {}
    for ficha in fichas_vinculadas:
        fichas_por_usuario.setdefault(ficha.usuario_id, []).append(ficha)

    for participante in CampanhaParticipante.objects.filter(
        campanha=campanha
    ).select_related("usuario"):
        fichas = fichas_por_usuario.get(participante.usuario_id, [])
        participantes.append(
            {
                "usuario": participante.usuario,
                "eh_mestre": participante.usuario_id == campanha.mestre_id,
                "online": bool(
                    participante.ultimo_acesso
                    and participante.ultimo_acesso >= agora - timedelta(seconds=90)
                ),
                "fichas": fichas,
                "espectador": (
                    participante.usuario_id != campanha.mestre_id and not fichas
                ),
            }
        )

    fichas_visiveis_campanha = [
        {
            "ficha": ficha,
            "pode_visualizar": (
                ficha.usuario_id == request.user.pk
                or eh_mestre
                or ficha.estrutura_json.get("visibilidade", "todos") == "todos"
            ),
        }
        for ficha in fichas_vinculadas
    ]
    fichas_disponiveis = FichaPersonagem.objects.filter(
        usuario=request.user
    ).exclude(vinculos_campanhas__campanha=campanha)
    arquivos_campanha = campanha.arquivos.all()
    arquivos_disponiveis = (
        Arquivo.objects.filter(usuario=request.user)
        .exclude(campanhas=campanha)
        if eh_mestre
        else Arquivo.objects.none()
    )
    templates_disponiveis = (
        TemplateFicha.objects.filter(usuario=request.user)
        if eh_mestre
        else TemplateFicha.objects.none()
    )
    sessao_atual = SessaoCampanha.objects.filter(
        campanha=campanha,
        encerrada_em__isnull=True,
    ).first()
    personagens_faltosos_sessao = (
        personagens_faltosos(sessao_atual) if sessao_atual else []
    )

    return render(
        request,
        "campanha.html",
        {
            "campanha": campanha,
            "eh_mestre": eh_mestre,
            "participantes": participantes,
            "fichas_campanha": fichas_visiveis_campanha,
            "fichas_disponiveis": fichas_disponiveis,
            "arquivos_campanha": arquivos_campanha,
            "arquivos_disponiveis": arquivos_disponiveis,
            "templates_disponiveis": templates_disponiveis,
            "template_mestre": campanha.template_mestre,
            "sessao_atual": sessao_atual,
            "personagens_faltosos": personagens_faltosos_sessao,
            "historico_sessoes": (
                campanha.sessoes.all() if eh_mestre else SessaoCampanha.objects.none()
            ),
            "presenca_url": reverse("api_presenca_campanha", args=[campanha.pk]),
            "iniciar_sessao_url": reverse(
                "iniciar_sessao_campanha",
                args=[campanha.pk],
            ),
            "parar_sessao_url": reverse(
                "parar_sessao_campanha",
                args=[campanha.pk],
            ),
            "chatbot_url": (
                reverse("api_chatbot_campanha", args=[campanha.pk])
                if sessao_atual
                else ""
            ),
        },
    )


@login_required
@require_POST
def excluir_campanha_view(request, campanha_id):
    campanha = _campanha_do_mestre(request, campanha_id)
    campanha.delete()
    messages.success(request, "Campanha excluída.")
    return redirect("campanhas")


@login_required
@require_POST
def sair_campanha_view(request, campanha_id):
    campanha = _campanha_propria(request, campanha_id)
    try:
        sair_da_campanha(campanha, request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Você saiu da campanha.")
    return redirect("campanhas")


@login_required
@require_POST
def remover_participante_view(request, campanha_id, usuario_id):
    campanha = _campanha_do_mestre(request, campanha_id)
    usuario = get_object_or_404(Usuario, pk=usuario_id)
    try:
        remover_participante(campanha, usuario)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, f"{usuario.username} foi removido da campanha.")
    return _redirecionar_campanha(campanha)


@login_required
@require_POST
def vincular_ficha_campanha_view(request, campanha_id):
    campanha = _campanha_propria(request, campanha_id)
    try:
        ficha = FichaPersonagem.objects.get(
            pk=request.POST.get("ficha_id"),
            usuario=request.user,
        )
    except (FichaPersonagem.DoesNotExist, ValueError, TypeError):
        messages.error(request, "Selecione uma ficha sua válida.")
        return _redirecionar_campanha(campanha)
    if not CampanhaParticipante.objects.filter(
        campanha=campanha,
        usuario=request.user,
    ).exists():
        messages.error(request, "Participe da campanha antes de vincular uma ficha.")
    else:
        FichaCampanha.objects.get_or_create(campanha=campanha, ficha=ficha)
        messages.success(request, f"A ficha “{ficha.nome}” foi vinculada.")
    return _redirecionar_campanha(campanha)


@login_required
@require_POST
def remover_ficha_campanha_view(request, campanha_id, ficha_id):
    campanha = _campanha_propria(request, campanha_id)
    vinculo = get_object_or_404(
        FichaCampanha.objects.select_related("ficha"),
        campanha=campanha,
        ficha_id=ficha_id,
    )
    if campanha.mestre_id != request.user.pk and vinculo.ficha.usuario_id != request.user.pk:
        messages.error(request, "Você não pode remover esta ficha da campanha.")
    else:
        vinculo.delete()
        messages.success(request, "Vínculo da ficha removido.")
    return _redirecionar_campanha(campanha)


@login_required
@require_POST
def vincular_arquivo_campanha_view(request, campanha_id):
    campanha = _campanha_do_mestre(request, campanha_id)
    arquivo = get_object_or_404(
        Arquivo.objects.filter(usuario=request.user),
        pk=request.POST.get("arquivo_id"),
    )
    campanha.arquivos.add(arquivo)
    messages.success(request, "Arquivo disponibilizado para a campanha.")
    return _redirecionar_campanha(campanha)


@login_required
@require_POST
def remover_arquivo_campanha_view(request, campanha_id, arquivo_id):
    campanha = _campanha_do_mestre(request, campanha_id)
    arquivo = get_object_or_404(campanha.arquivos.all(), pk=arquivo_id)
    campanha.arquivos.remove(arquivo)
    messages.success(request, "Arquivo removido da campanha.")
    return _redirecionar_campanha(campanha)


@login_required
@require_POST
def vincular_template_campanha_view(request, campanha_id):
    campanha = _campanha_do_mestre(request, campanha_id)
    template = get_object_or_404(
        TemplateFicha.objects.filter(usuario=request.user),
        pk=request.POST.get("template_id"),
    )
    campanha.template_mestre = template
    campanha.save(update_fields=["template_mestre", "atualizada_em"])
    messages.success(request, "Template do mestre disponibilizado.")
    return _redirecionar_campanha(campanha)


@login_required
@require_POST
def remover_template_campanha_view(request, campanha_id):
    campanha = _campanha_do_mestre(request, campanha_id)
    campanha.template_mestre = None
    campanha.save(update_fields=["template_mestre", "atualizada_em"])
    messages.success(request, "Template removido da campanha.")
    return _redirecionar_campanha(campanha)


@login_required
@require_POST
def copiar_template_campanha_view(request, campanha_id):
    campanha = _campanha_propria(request, campanha_id)
    template = campanha.template_mestre
    if template is None:
        messages.error(request, "Esta campanha não disponibiliza um template.")
    else:
        TemplateFicha.objects.create(
            usuario=request.user,
            nome=template.nome,
            estrutura_json=template.estrutura_json,
        )
        messages.success(request, "Template copiado para sua conta.")
    return _redirecionar_campanha(campanha)


def _resposta_presenca(campanha):
    limite_online = timezone.now() - timedelta(seconds=90)
    return [
        {
            "id": vinculo.usuario_id,
            "online": bool(
                vinculo.ultimo_acesso and vinculo.ultimo_acesso >= limite_online
            ),
        }
        for vinculo in CampanhaParticipante.objects.filter(
            campanha=campanha
        ).only("usuario_id", "ultimo_acesso")
    ]


@login_required
@require_POST
def api_presenca_campanha(request, campanha_id):
    campanha = _campanha_propria(request, campanha_id)
    CampanhaParticipante.objects.filter(
        campanha=campanha,
        usuario=request.user,
    ).update(ultimo_acesso=timezone.now())
    return JsonResponse({"participantes": _resposta_presenca(campanha)})


@login_required
@require_POST
def iniciar_sessao_campanha_view(request, campanha_id):
    campanha = _campanha_do_mestre(request, campanha_id)
    try:
        sessao = iniciar_sessao(campanha)
    except ValidationError as error:
        return JsonResponse({"erro": " ".join(error.messages)}, status=409)
    return JsonResponse(
        {
            "id": sessao.pk,
            "iniciada_em": sessao.iniciada_em.isoformat(),
            "participantes": sessao.participantes_json,
        },
        status=201,
    )


@login_required
@require_POST
def parar_sessao_campanha_view(request, campanha_id):
    campanha = _campanha_do_mestre(request, campanha_id)
    try:
        sessao = parar_sessao(campanha)
    except ValidationError as error:
        return JsonResponse({"erro": " ".join(error.messages)}, status=409)
    gerar_relatorio(sessao)
    return JsonResponse(
        {
            "id": sessao.pk,
            "encerrada_em": sessao.encerrada_em.isoformat(),
            "duracao_segundos": sessao.duracao_segundos,
        }
    )


@login_required
@require_POST
def api_chatbot_campanha(request, campanha_id):
    campanha = _campanha_do_mestre(request, campanha_id)
    sessao = SessaoCampanha.objects.filter(
        campanha=campanha,
        encerrada_em__isnull=True,
    ).first()
    if sessao is None:
        return JsonResponse(
            {"erro": "Inicie uma sessão antes de usar o chatbot."},
            status=409,
        )
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}
    comando = str(payload.get("comando", "")).strip()
    if not comando:
        return JsonResponse(
            {"erro": "Informe um comando para o chatbot."},
            status=400,
        )
    if len(comando) > 4000:
        return JsonResponse(
            {"erro": "O comando deve ter no máximo 4.000 caracteres."},
            status=400,
        )
    return JsonResponse(enviar_comando(sessao, comando))


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "Sessão encerrada.")
    return redirect("inicio")


@login_required
def pagina_provisoria(_request, **_kwargs):
    return HttpResponse("")
