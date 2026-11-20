import copy
import json
import logging
import mimetypes
import os
import posixpath
import uuid
from functools import wraps
from types import SimpleNamespace

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect
from django.template import engines
from django.urls import reverse
from django.utils.http import content_disposition_header, url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib.auth.password_validation import validate_password
from markupsafe import Markup

from .models import Campaign, CharacterSheet, LibraryBook, PlayerProfile, SheetTemplate
from .character_ai import (
    CharacterAssistantUnavailable,
    InvalidCharacterSuggestion,
    generate_character_suggestion,
)

User = get_user_model()
logger = logging.getLogger(__name__)
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
ALLOWED_LIBRARY_EXTENSIONS = {"pdf", *ALLOWED_IMAGE_EXTENSIONS}
MAX_AVATAR_SIZE = 5 * 1024 * 1024
MAX_LIBRARY_FILE_SIZE = 16 * 1024 * 1024
MAX_SHEET_JSON_SIZE = 1 * 1024 * 1024
SHEET_COMPONENT_TYPES = {
    "InformacaoCurta",
    "Contador",
    "Checkbox",
    "AtributoSimples",
    "AtributoDuplo",
    "AtributoComplexo",
    "AnotacaoSimples",
    "AnotacaoCheckbox",
    "AnotacaoDetalhada",
}


def _profile(user):
    profile, _ = PlayerProfile.objects.get_or_create(
        user=user,
        defaults={
            "display_name": user.get_full_name() or user.username.split("@")[0],
            "email": user.email.strip().lower(),
        },
    )
    return profile


def _render(request, template_name, context=None):
    context = dict(context or {})
    profile = _profile(request.user) if request.user.is_authenticated else None
    context.setdefault("usuario", profile)
    context.setdefault("mostrar_chave_teste", settings.DEBUG)
    context["g"] = SimpleNamespace(usuario=profile)
    context["request"] = request
    csrf_token = get_token(request)
    context["csrf_input"] = Markup(
        f'<input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}">'
    )

    def get_flashed_messages(with_categories=False):
        queued = list(messages.get_messages(request))
        if with_categories:
            return [(message.extra_tags or "info", str(message)) for message in queued]
        return [str(message) for message in queued]

    context["get_flashed_messages"] = get_flashed_messages
    template = engines["jinja2"].get_template(template_name)
    return HttpResponse(template.render(context, request))


def _flash(request, text, category="info"):
    levels = {
        "sucesso": messages.SUCCESS,
        "perigo": messages.ERROR,
        "aviso": messages.WARNING,
        "info": messages.INFO,
    }
    messages.add_message(request, levels.get(category, messages.INFO), text, extra_tags=category)


def _key_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not _profile(request.user).activated:
            _flash(request, "Esta funcionalidade exige o resgate de uma chave de produto válida.", "aviso")
            return redirect("colecoes")
        return view(request, *args, **kwargs)

    return wrapped


def _safe_upload_name(upload, extensions):
    name = os.path.basename(upload.name or "")
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in extensions:
        return None
    return name


def _valid_upload_content(upload, extension):
    header = upload.read(16)
    upload.seek(0)
    if extension == "pdf":
        return header.startswith(b"%PDF-")
    if extension == "png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {"jpg", "jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    return False


def _can_create_sheet(user):
    return _profile(user).activated or not CharacterSheet.objects.filter(owner=user).exists()


def _active_campaign_memberships(user):
    return Campaign.objects.filter(models_q_campaign_access(user.pk)).distinct()


def _default_structure(name="Novo Personagem", subtitle=""):
    return {
        "id": None,
        "nome": name,
        "subtitulo": subtitle,
        "avatar": None,
        "visibilidade": "todos",
        "colunas": {
            "1": {
                "ativa": True,
                "abaAtivaId": 1000,
                "abas": [{"id": 1000, "titulo": "Geral", "ehPadrao": True, "secoes": []}],
            },
            "2": {"ativa": True, "abaAtivaId": None, "abas": []},
            "3": {"ativa": True, "abaAtivaId": None, "abas": []},
        },
    }


def _sheet_payload(sheet):
    data = copy.deepcopy(sheet.structure) if isinstance(sheet.structure, dict) else {}
    if not data:
        data = _default_structure(sheet.name, sheet.subtitle)
    data["id"] = sheet.pk
    data["nome"] = sheet.name
    data["subtitulo"] = sheet.subtitle
    data["avatar"] = sheet.avatar_path or None
    data["visibilidade"] = sheet.visibility
    data.setdefault("colunas", _default_structure()["colunas"])
    return data


def _save_sheet_payload(sheet, data):
    if not isinstance(data, dict):
        raise ValueError("O corpo da ficha deve ser um objeto JSON.")
    columns = data.get("colunas", {})
    if not isinstance(columns, dict):
        raise ValueError("A estrutura de colunas é inválida.")
    for position in ("1", "2", "3"):
        column = columns.setdefault(position, {"ativa": True, "abaAtivaId": None, "abas": []})
        if not isinstance(column, dict):
            raise ValueError("A estrutura de abas é inválida.")
        column.setdefault("abas", [])
        if not isinstance(column["abas"], list):
            raise ValueError("A estrutura de abas é inválida.")
        if len(column["abas"]) > 3:
            raise ValueError("Cada coluna pode conter no máximo três abas.")
        for tab in column.get("abas", []):
            if not isinstance(tab, dict):
                raise ValueError("A estrutura de seções é inválida.")
            tab.setdefault("secoes", [])
            if not isinstance(tab["secoes"], list) or len(tab["secoes"]) > 100:
                raise ValueError("A estrutura de seções é inválida.")
            for section in tab.get("secoes", []):
                if not isinstance(section, dict):
                    raise ValueError("A estrutura de componentes é inválida.")
                section.setdefault("componentes", [])
                section_type = section.get("tipo", "AtributoSimples")
                if (
                    not isinstance(section["componentes"], list)
                    or len(section["componentes"]) > 200
                    or not isinstance(section_type, str)
                    or section_type not in SHEET_COMPONENT_TYPES
                ):
                    raise ValueError("A estrutura de componentes é inválida.")
                if any(not isinstance(component, dict) for component in section["componentes"]):
                    raise ValueError("A estrutura de componentes é inválida.")
    if not columns["1"]["abas"]:
        raise ValueError("A primeira coluna deve manter pelo menos uma aba.")
    columns["1"]["abas"][0]["ehPadrao"] = True
    data["colunas"] = {key: columns[key] for key in ("1", "2", "3")}
    data["id"] = sheet.pk
    name = str(data.get("nome") or "").strip()
    if not name:
        raise ValueError("O nome do personagem não pode ficar vazio.")
    sheet.name = name[:100]
    sheet.subtitle = str(data.get("subtitulo") or data.get("aspecto") or "")[:100]
    sheet.visibility = "mestres" if data.get("visibilidade") == "mestres" else "todos"
    data["nome"] = sheet.name
    data["subtitulo"] = sheet.subtitle
    if "avatar" in data:
        avatar = data["avatar"]
        allowed_avatar_prefix = f"{settings.MEDIA_URL}avatars/characters/{sheet.pk}_"
        if avatar is not None and (
            not isinstance(avatar, str) or not avatar.startswith(allowed_avatar_prefix)
        ):
            raise ValueError("O endereço do avatar não é válido.")
        sheet.avatar_path = avatar or ""
    data["avatar"] = sheet.avatar_path or None
    data["visibilidade"] = sheet.visibility
    sheet.structure = data
    sheet.save(update_fields=["name", "subtitle", "avatar_path", "visibility", "structure"])


def _sheet_access(sheet, user_id):
    if sheet.owner_id == user_id:
        return True, True
    campaigns = sheet.campaigns.filter(
        models_q_campaign_access(user_id)
    )
    if sheet.visibility == "mestres":
        return campaigns.filter(master_id=user_id).exists(), False
    return campaigns.exists(), False


def models_q_campaign_access(user_id):
    from django.db.models import Q

    return Q(master_id=user_id) | Q(players__id=user_id)


def _json_body(request):
    try:
        value = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _next_structure_id(data):
    maximum = 1000
    for column in data.get("colunas", {}).values():
        for tab in column.get("abas", []):
            for item in [tab, *tab.get("secoes", [])]:
                if isinstance(item.get("id"), int):
                    maximum = max(maximum, item["id"])
                for component in item.get("componentes", []):
                    if isinstance(component.get("id"), int):
                        maximum = max(maximum, component["id"])
    return maximum + 1


def _find_sheet_section(data, section_id):
    for column in data["colunas"].values():
        for tab in column["abas"]:
            for section in tab["secoes"]:
                if section.get("id") == section_id:
                    return section
    return None


def _default_component(component_type, data, component_id):
    definitions = {
        "InformacaoCurta": {"rotulo": "", "campoTexto": ""},
        "Contador": {"rotulo": "", "valorAtual": 0, "valorMaximo": 10, "corSeletor": "#2b2631"},
        "Checkbox": {"rotulo": "", "estaMarcado": False},
        "AtributoSimples": {"nomeAtributo": "", "valorAtributo": 0},
        "AtributoDuplo": {"nomeAtributo": "", "valorGrande": 0, "valorPequeno": 0},
        "AtributoComplexo": {
            "nomeAtributo": "",
            "valorBase": 0,
            "valorBonus": 0,
            "valorOutros": 0,
            "subtituloAnotacao": "",
            "criterioOrdenacao": 0,
        },
        "AnotacaoSimples": {"rotulo": "", "descricao": ""},
        "AnotacaoCheckbox": {"rotulo": "", "descricao": "", "estaMarcado": False},
        "AnotacaoDetalhada": {"rotulo": "", "descricao": "", "anotacaoExtra": ""},
    }
    if component_type not in definitions:
        return None
    result = {"id": component_id, **definitions[component_type]}
    for key in definitions[component_type]:
        if key in data:
            result[key] = data[key]
    return result


def inicio(request):
    return _render(request, "inicio.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("colecoes")
    next_url = request.POST.get("next") or request.GET.get("next")
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        password = (request.POST.get("senha") or "").strip()
        if not email or not password:
            _flash(request, "Informe um e-mail e uma senha para continuar.", "perigo")
            return _render(request, "login.html", {"next_url": next_url})
        existing_user = User.objects.filter(email__iexact=email).first()
        user = (
            authenticate(request, username=existing_user.get_username(), password=password)
            if existing_user
            else None
        )
        if user is None:
            _flash(request, "E-mail ou senha inválidos. Se ainda não tem conta, faça seu cadastro.", "perigo")
            return _render(request, "login.html", {"next_url": next_url})
        login(request, user)
        _profile(user)
        _flash(request, f"Login realizado com sucesso, {_profile(user).display_name}!", "sucesso")
        if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
            return redirect(next_url)
        return redirect("colecoes")
    return _render(request, "login.html", {"next_url": next_url})


def cadastro(request):
    if request.user.is_authenticated:
        return redirect("colecoes")
    if request.method == "POST":
        name = (request.POST.get("nome") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("senha") or ""
        password_confirmation = request.POST.get("confirmar_senha") or ""
        if not name or not email or not password:
            _flash(request, "Preencha seu nome, e-mail e senha.", "perigo")
            return _render(request, "cadastro.html")
        if password != password_confirmation:
            _flash(request, "As senhas informadas não coincidem.", "perigo")
            return _render(request, "cadastro.html")
        if (
            PlayerProfile.objects.filter(email__iexact=email).exists()
            or User.objects.filter(email__iexact=email).exists()
            or User.objects.filter(username__iexact=email).exists()
        ):
            _flash(request, "Já existe uma conta cadastrada com este e-mail.", "perigo")
            return _render(request, "cadastro.html")
        user = User(username=email, email=email)
        try:
            validate_password(password, user)
            user.set_password(password)
            with transaction.atomic():
                user.save()
                PlayerProfile.objects.create(user=user, display_name=name[:100], email=email)
        except ValidationError as error:
            _flash(request, " ".join(error.messages), "perigo")
            return _render(request, "cadastro.html")
        except IntegrityError:
            _flash(request, "Já existe uma conta cadastrada com este e-mail.", "perigo")
            return _render(request, "cadastro.html")
        login(request, user)
        _flash(request, f"Conta criada com sucesso, {name}!", "sucesso")
        return redirect("colecoes")
    return _render(request, "cadastro.html")


@require_POST
def logout_view(request):
    logout(request)
    _flash(request, "Sessão encerrada.", "info")
    return redirect("inicio")


@login_required
def perfil(request):
    profile = _profile(request.user)
    if request.method == "POST":
        name = (request.POST.get("nome") or "").strip()
        if not name:
            _flash(request, "O nome não pode ficar vazio.", "perigo")
            return redirect("perfil")
        upload = request.FILES.get("avatar_arquivo")
        if upload:
            safe_name = _safe_upload_name(upload, ALLOWED_IMAGE_EXTENSIONS)
            extension = safe_name.rsplit(".", 1)[-1].lower() if safe_name else ""
            if (
                not safe_name
                or upload.size > MAX_AVATAR_SIZE
                or not _valid_upload_content(upload, extension)
            ):
                _flash(request, "Use um arquivo PNG, JPG ou JPEG válido de até 5 MB.", "perigo")
                return redirect("perfil")
            profile.avatar.save(f"user_{request.user.pk}_{uuid.uuid4().hex[:8]}_{safe_name}", upload, save=False)
        profile.display_name = name[:100]
        profile.save()
        _flash(request, "Perfil atualizado com sucesso!", "sucesso")
        return redirect("perfil")
    return _render(request, "perfil.html", {"usuario": profile})


@login_required
@require_POST
def resgate(request):
    if request.POST.get("chave_produto") == settings.RPG_ACTIVATION_KEY:
        profile = _profile(request.user)
        profile.activated = True
        profile.save(update_fields=["activated"])
        _flash(request, "Chave de produto ativada com sucesso! Funcionalidades desbloqueadas.", "sucesso")
    else:
        _flash(request, "A chave informada é inválida ou não pode ser resgatada.", "perigo")
    return redirect(request.META.get("HTTP_REFERER") or reverse("colecoes"))


@login_required
def colecoes(request):
    user_campaigns = Campaign.objects.filter(
        models_q_campaign_access(request.user.pk)
    ).distinct()
    sheets = CharacterSheet.objects.filter(owner=request.user).order_by("-created_at")
    return _render(
        request,
        "colecoes.html",
        {
            "campanhas": user_campaigns,
            "fichas": sheets,
            "pode_criar_ficha": _can_create_sheet(request.user),
            "pode_entrar_campanha": _profile(request.user).activated
            or not _active_campaign_memberships(request.user).exists(),
        },
    )


@login_required
@_key_required
def criar_campanha(request):
    if not _profile(request.user).activated:
        return redirect("colecoes")
    if request.method == "POST":
        name = (request.POST.get("nome") or "").strip()
        if not name:
            _flash(request, "O nome da campanha é obrigatório.", "perigo")
        else:
            campaign = Campaign.objects.create(
                name=name[:100],
                description=(request.POST.get("descricao") or "").strip(),
                master=request.user,
            )
            campaign.players.add(request.user)
            _flash(request, f"Campanha '{campaign.name}' criada com sucesso!", "sucesso")
            return redirect("campanha_detalhes", id_campanha=campaign.pk)
    return _render(request, "criarCampanha.html")


@login_required
@require_POST
def entrar_campanha(request):
    invite_code = (request.POST.get("codigo_campanha") or "").strip().upper()
    try:
        campaign = Campaign.objects.get(invite_code__iexact=invite_code)
    except Campaign.DoesNotExist:
        _flash(request, "Campanha não encontrada com o código fornecido.", "perigo")
        return redirect("colecoes")
    if campaign.players.filter(pk=request.user.pk).exists():
        return redirect("campanha_detalhes", id_campanha=campaign.pk)
    if not _profile(request.user).activated and _active_campaign_memberships(request.user).exists():
        _flash(request, "Usuários sem licença podem participar de apenas uma campanha por vez.", "aviso")
        return redirect("colecoes")
    campaign.players.add(request.user)
    _flash(request, f"Você entrou com sucesso na campanha '{campaign.name}'!", "sucesso")
    return redirect("campanha_detalhes", id_campanha=campaign.pk)


@login_required
def campanha_detalhes(request, id_campanha):
    campaign = get_object_or_404(Campaign, pk=id_campanha)
    if request.user.pk != campaign.master_id and not campaign.players.filter(pk=request.user.pk).exists():
        _flash(request, "Você não participa desta campanha.", "perigo")
        return redirect("colecoes")
    is_master = request.user.pk == campaign.master_id
    if request.method == "POST":
        if not is_master:
            _flash(request, "Apenas o mestre pode editar os dados desta campanha.", "perigo")
        elif not (request.POST.get("nome") or "").strip():
            _flash(request, "O nome da campanha não pode ficar vazio.", "perigo")
        else:
            campaign.name = request.POST["nome"].strip()[:100]
            campaign.description = (request.POST.get("descricao") or "").strip()
            campaign.save(update_fields=["name", "description"])
            _flash(request, "Dados da campanha atualizados com sucesso!", "sucesso")
        return redirect("campanha_detalhes", id_campanha=campaign.pk)

    linked_sheets = campaign.characters.select_related("owner").all()
    linked_ids = linked_sheets.values_list("pk", flat=True)
    available_sheets = CharacterSheet.objects.filter(owner=request.user).exclude(pk__in=linked_ids)
    books = [
        {"id": book.pk, "nome": book.name, "url": reverse("livro_arquivo", args=[book.pk])}
        for book in campaign.library_books.all()
    ]
    participants = []
    for profile in campaign.jogadores:
        if profile.id == campaign.master_id:
            continue
        characters = list(linked_sheets.filter(owner_id=profile.id))
        participants.append(
            {
                "usuario": profile,
                "role": "Jogador" if characters else "Espectador",
                "detalhe": f"{len(characters)} personagem{'s' if len(characters) != 1 else ''} vinculado{'s' if len(characters) != 1 else ''}"
                if characters
                else "Nenhuma ficha vinculada",
                "fichas": characters,
            }
        )
    return _render(
        request,
        "campanha.html",
        {
            "campanha": campaign,
            "mestre": _profile(campaign.master),
            "fichas_campanha": linked_sheets,
            "fichas_disponiveis": available_sheets,
            "livros_campanha": books,
            "biblioteca_pessoal": sorted(
                LibraryBook.objects.filter(owner=request.user),
                key=lambda book: book.name.lower(),
            ),
            "participantes": participants,
        },
    )


@login_required
@require_POST
def anexar_arquivo_campanha(request, id_campanha):
    campaign = get_object_or_404(Campaign, pk=id_campanha)
    if campaign.master_id != request.user.pk:
        _flash(request, "Somente o mestre pode anexar arquivos à campanha.", "perigo")
    else:
        book = LibraryBook.objects.filter(
            owner=request.user, pk=request.POST.get("arquivo_campanha")
        ).first()
        if not book:
            _flash(request, "Selecione um arquivo existente na sua biblioteca.", "perigo")
        else:
            campaign.library_books.add(book)
            _flash(request, "Arquivo anexado à campanha com sucesso!", "sucesso")
    return redirect("campanha_detalhes", id_campanha=id_campanha)


@login_required
@require_POST
def remover_arquivo_campanha(request, id_campanha):
    campaign = get_object_or_404(Campaign, pk=id_campanha)
    if campaign.master_id == request.user.pk:
        book = campaign.library_books.filter(pk=request.POST.get("arquivo_id")).first()
        if book:
            campaign.library_books.remove(book)
            _flash(request, "Vínculo de arquivo removido com sucesso!", "sucesso")
        else:
            _flash(request, "Arquivo não vinculado a esta campanha.", "perigo")
    else:
        _flash(request, "Somente o mestre pode remover arquivos da campanha.", "perigo")
    return redirect("campanha_detalhes", id_campanha=id_campanha)


@login_required
@require_POST
def vincular_ficha_campanha(request, id_campanha):
    campaign = get_object_or_404(Campaign, pk=id_campanha)
    sheet = get_object_or_404(CharacterSheet, pk=request.POST.get("ficha_id"), owner=request.user)
    campaign.players.add(request.user)
    campaign.characters.add(sheet)
    _flash(request, f"A ficha '{sheet.name}' foi vinculada à campanha.", "sucesso")
    return redirect("campanha_detalhes", id_campanha=id_campanha)


@login_required
@require_POST
def remover_ficha_campanha(request, id_campanha):
    campaign = get_object_or_404(Campaign, pk=id_campanha)
    sheet = get_object_or_404(campaign.characters, pk=request.POST.get("ficha_id"))
    if campaign.master_id == request.user.pk or sheet.owner_id == request.user.pk:
        campaign.characters.remove(sheet)
        _flash(request, "Personagem removido da campanha.", "sucesso")
    else:
        _flash(request, "Você não tem permissão para remover esta ficha.", "perigo")
    return redirect("campanha_detalhes", id_campanha=id_campanha)


@login_required
def livros(request):
    if request.method == "POST" and request.POST.get("deletar_livro"):
        book = LibraryBook.objects.filter(
            owner=request.user, pk=request.POST["deletar_livro"]
        ).first()
        if book:
            book.file.delete(save=False)
            book.delete()
            _flash(request, "Livro removido com sucesso!", "sucesso")
        else:
            _flash(request, "Arquivo não encontrado.", "perigo")
        return redirect("livros")
    if request.method == "POST":
        upload = request.FILES.get("livro_pdf")
        if not upload:
            _flash(request, "Nenhum arquivo enviado.", "perigo")
        else:
            safe_name = _safe_upload_name(upload, ALLOWED_LIBRARY_EXTENSIONS)
            extension = safe_name.rsplit(".", 1)[-1].lower() if safe_name else ""
            if (
                not safe_name
                or upload.size > MAX_LIBRARY_FILE_SIZE
                or not _valid_upload_content(upload, extension)
            ):
                _flash(request, "Envie um PDF, PNG ou JPG/JPEG válido de até 16 MB.", "perigo")
            else:
                book = LibraryBook(owner=request.user)
                book.file.save(safe_name, upload, save=True)
                _flash(request, "Arquivo adicionado à biblioteca com sucesso!", "sucesso")
                return redirect("livros")
    books = [
        {
            "id": book.pk,
            "name": book.name,
            "url": reverse("livro_arquivo", args=[book.pk]),
            "extension": book.name.rsplit(".", 1)[-1].lower(),
        }
        for book in LibraryBook.objects.filter(owner=request.user).order_by("file")
    ]
    return _render(request, "livros.html", {"livros": books})


@login_required
def selecao_personagens(request):
    sheets = CharacterSheet.objects.filter(owner=request.user).order_by("-created_at")
    return _render(
        request,
        "gerenciarPersonagens.html",
        {
            "fichas": sheets,
            "usuario": _profile(request.user),
            "pode_criar_ficha": _can_create_sheet(request.user),
            "assistente_ia_disponivel": bool(settings.GOOGLE_API_KEY),
        },
    )


@login_required
@require_POST
def api_assistente_personagem(request):
    if not _can_create_sheet(request.user):
        return JsonResponse({"erro": "Sua conta atingiu o limite de criação de fichas."}, status=403)
    if len(request.body) > 8 * 1024:
        return JsonResponse({"erro": "A solicitação excede o limite permitido."}, status=413)
    data = _json_body(request)
    idea = data.get("ideia") if data else None
    if not isinstance(idea, str) or not idea.strip():
        return JsonResponse({"erro": "Descreva uma ideia para o personagem."}, status=400)
    idea = idea.strip()
    if len(idea) > 500:
        return JsonResponse({"erro": "A ideia deve ter no máximo 500 caracteres."}, status=400)

    try:
        suggestion = generate_character_suggestion(idea)
    except CharacterAssistantUnavailable:
        return JsonResponse(
            {"erro": "O assistente de IA não está configurado. Defina GOOGLE_API_KEY."},
            status=503,
        )
    except InvalidCharacterSuggestion:
        logger.warning("Gemini returned an invalid character suggestion.")
        return JsonResponse(
            {"erro": "A IA não retornou uma sugestão válida. Tente novamente."},
            status=502,
        )
    except Exception:
        logger.exception("Failed to generate a character suggestion.")
        return JsonResponse(
            {"erro": "Não foi possível gerar uma sugestão agora. Tente novamente."},
            status=502,
        )
    return JsonResponse(suggestion)


@login_required
def selecao_criacao(request):
    return redirect("selecao_personagens")


@login_required
@require_POST
def excluir_personagem(request, id_ficha):
    sheet = get_object_or_404(CharacterSheet, pk=id_ficha, owner=request.user)
    sheet.delete()
    _flash(request, "Personagem excluído com sucesso!", "sucesso")
    return redirect("selecao_personagens")


@login_required
@require_POST
def criar_ficha(request):
    if not _can_create_sheet(request.user):
        _flash(request, "Contas sem licença podem criar apenas uma ficha.", "aviso")
        return redirect("selecao_personagens")
    name = (request.POST.get("nome_personagem") or "").strip()
    if not name:
        _flash(request, "O nome do personagem é obrigatório.", "perigo")
        return redirect("selecao_personagens")
    subtitle = (request.POST.get("subtitulo") or "").strip()
    sheet = CharacterSheet.objects.create(owner=request.user, name=name[:100], subtitle=subtitle[:100])
    data = _default_structure(sheet.name, sheet.subtitle)
    data["id"] = sheet.pk
    sheet.structure = data
    sheet.save(update_fields=["structure"])
    _flash(request, f"Personagem '{sheet.name}' criado com sucesso!", "sucesso")
    return redirect("criador_ficha", id_ficha=sheet.pk)


@login_required
def criador_ficha(request, id_ficha):
    sheet = get_object_or_404(CharacterSheet, pk=id_ficha)
    visible, editable = _sheet_access(sheet, request.user.pk)
    if not visible:
        _flash(request, "Você não tem permissão para acessar esta ficha.", "perigo")
        return redirect("colecoes")
    return _render(
        request,
        "criarPersonagem.html",
        {"ficha": sheet, "pode_editar": editable, "modo_inicial": "Jogo"},
    )


@login_required
def gerenciar_campanhas(request):
    campaigns = Campaign.objects.filter(models_q_campaign_access(request.user.pk)).distinct()
    return _render(request, "gerenciarCampanhas.html", {"campanhas": campaigns, "usuario": _profile(request.user)})


@login_required
@require_POST
def excluir_campanha(request, id_campanha):
    campaign = get_object_or_404(Campaign, pk=id_campanha)
    if campaign.master_id != request.user.pk:
        _flash(request, "Você não tem permissão para excluir esta campanha.", "perigo")
    else:
        campaign.delete()
        _flash(request, "Campanha excluída com sucesso!", "sucesso")
    return redirect("gerenciar_campanhas")


@login_required
@require_POST
def sair_campanha(request, id_campanha):
    campaign = get_object_or_404(Campaign, pk=id_campanha)
    if campaign.master_id == request.user.pk:
        _flash(request, "O mestre não pode sair da campanha. Use a opção de excluir.", "perigo")
    else:
        campaign.players.remove(request.user)
        campaign.characters.remove(*campaign.characters.filter(owner=request.user))
        _flash(request, "Você saiu da campanha com sucesso!", "sucesso")
    return redirect("gerenciar_campanhas")


@login_required
@require_POST
def remover_participante(request, id_campanha, participante_id):
    campaign = get_object_or_404(Campaign, pk=id_campanha)
    if campaign.master_id != request.user.pk:
        _flash(request, "Somente o mestre pode remover participantes.", "perigo")
    elif participante_id == campaign.master_id:
        _flash(request, "O mestre não pode ser removido da própria campanha.", "perigo")
    elif not campaign.players.filter(pk=participante_id).exists():
        _flash(request, "Participante não encontrado nesta campanha.", "perigo")
    else:
        campaign.players.remove(participante_id)
        campaign.characters.remove(*campaign.characters.filter(owner_id=participante_id))
        _flash(request, "Participante removido da campanha.", "sucesso")
    return redirect("campanha_detalhes", id_campanha=id_campanha)


@login_required
def livro_arquivo(request, livro_id):
    book = get_object_or_404(LibraryBook, pk=livro_id)
    is_owner = book.owner_id == request.user.pk
    has_campaign_access = book.campaigns.filter(
        models_q_campaign_access(request.user.pk)
    ).exists()
    if not is_owner and not has_campaign_access:
        raise Http404
    try:
        content = default_storage.open(book.file.name, "rb")
    except (OSError, ValueError):
        raise Http404 from None
    content_type = mimetypes.guess_type(book.name)[0] or "application/octet-stream"
    response = FileResponse(content, content_type=content_type)
    response["Content-Disposition"] = content_disposition_header(False, book.name)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
def arquivo_midia(request, caminho):
    normalized_path = posixpath.normpath(caminho)
    if normalized_path.startswith("../") or normalized_path.startswith("/") or normalized_path != caminho:
        raise Http404
    if normalized_path.startswith("library/"):
        book = LibraryBook.objects.filter(file=normalized_path).first()
        if not book:
            raise Http404
        is_owner = book.owner_id == request.user.pk
        has_campaign_access = book.campaigns.filter(
            models_q_campaign_access(request.user.pk)
        ).exists()
        if not is_owner and not has_campaign_access:
            raise Http404
        content_type = mimetypes.guess_type(book.name)[0] or "application/octet-stream"
    elif normalized_path.startswith("avatars/users/"):
        if not PlayerProfile.objects.filter(avatar=normalized_path).exists():
            raise Http404
        content_type = mimetypes.guess_type(normalized_path)[0] or "application/octet-stream"
    elif normalized_path.startswith("avatars/characters/"):
        sheet = CharacterSheet.objects.filter(
            avatar_path=f"{settings.MEDIA_URL}{normalized_path}"
        ).first()
        if not sheet or not _sheet_access(sheet, request.user.pk)[0]:
            raise Http404
        content_type = mimetypes.guess_type(normalized_path)[0] or "application/octet-stream"
    else:
        raise Http404
    try:
        content = default_storage.open(normalized_path, "rb")
    except (OSError, ValueError):
        raise Http404 from None
    response = FileResponse(content, content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_http_methods(["GET", "POST"])
def api_ficha(request, id_ficha):
    if request.method == "POST":
        return api_salvar_ficha(request, id_ficha)
    sheet = CharacterSheet.objects.filter(pk=id_ficha).first()
    if not sheet:
        return JsonResponse({"erro": "Ficha não encontrada."}, status=404)
    visible, _ = _sheet_access(sheet, request.user.pk)
    if not visible:
        return JsonResponse({"erro": "Acesso negado."}, status=403)
    return JsonResponse(_sheet_payload(sheet))


@login_required
@require_POST
def api_salvar_ficha(request, id_ficha):
    sheet = CharacterSheet.objects.filter(pk=id_ficha).first()
    if not sheet:
        return JsonResponse({"erro": "Ficha não encontrada."}, status=404)
    _, editable = _sheet_access(sheet, request.user.pk)
    if not editable:
        return JsonResponse({"erro": "Acesso negado."}, status=403)
    if len(request.body) > MAX_SHEET_JSON_SIZE:
        return JsonResponse({"erro": "A ficha excede o limite de 1 MB."}, status=413)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"erro": "Dados JSON inválidos."}, status=400)
    try:
        _save_sheet_payload(sheet, data)
    except ValueError as error:
        return JsonResponse({"erro": str(error)}, status=400)
    return JsonResponse({"status": "success"})


@login_required
@require_POST
def api_upload_avatar_personagem(request, id_ficha):
    sheet = CharacterSheet.objects.filter(pk=id_ficha, owner=request.user).first()
    if not sheet:
        return JsonResponse({"erro": "Ficha não encontrada ou acesso negado."}, status=404)
    upload = request.FILES.get("avatar")
    if not upload:
        return JsonResponse({"erro": "Nenhum arquivo enviado."}, status=400)
    safe_name = _safe_upload_name(upload, ALLOWED_IMAGE_EXTENSIONS)
    extension = safe_name.rsplit(".", 1)[-1].lower() if safe_name else ""
    if (
        not safe_name
        or upload.size > MAX_AVATAR_SIZE
        or not _valid_upload_content(upload, extension)
    ):
        return JsonResponse({"erro": "Use uma imagem PNG, JPG ou JPEG válida de até 5 MB."}, status=400)
    path = default_storage.save(f"avatars/characters/{sheet.pk}_{uuid.uuid4().hex[:8]}_{safe_name}", upload)
    sheet.avatar_path = default_storage.url(path)
    data = _sheet_payload(sheet)
    data["avatar"] = sheet.avatar_path
    sheet.structure = data
    sheet.save(update_fields=["avatar_path", "structure"])
    return JsonResponse(
        {"status": "success", "avatar_url": sheet.avatar_path, "message": "Avatar atualizado com sucesso!"}
    )


@login_required
def api_listar_templates(request, id_ficha):
    sheet = CharacterSheet.objects.filter(pk=id_ficha).first()
    if not sheet:
        return JsonResponse({"erro": "Ficha não encontrada."}, status=404)
    visible, _ = _sheet_access(sheet, request.user.pk)
    if not visible:
        return JsonResponse({"erro": "Acesso negado."}, status=403)
    templates = SheetTemplate.objects.filter(owner=request.user).order_by("name")
    return JsonResponse(
        {
            "templates": [
                {"id": item.pk, "nome": item.name, "estrutura_json": item.structure}
                for item in templates
            ]
        }
    )


@login_required
@require_POST
def api_criar_template(request, id_ficha):
    sheet = CharacterSheet.objects.filter(pk=id_ficha, owner=request.user).first()
    if not sheet:
        return JsonResponse({"erro": "Ficha não encontrada."}, status=404)
    data = _json_body(request) or {}
    name = str(data.get("nome") or request.POST.get("nome") or "").strip()
    if not name:
        return JsonResponse({"erro": "Informe um nome para o template."}, status=400)
    template = SheetTemplate.objects.create(
        owner=request.user,
        source_sheet=sheet,
        name=name[:100],
        structure=_sheet_payload(sheet),
    )
    return JsonResponse({"status": "success", "id": template.pk, "nome": template.name})


def _renew_template_ids(data):
    result = copy.deepcopy(data)
    next_id = 1000
    tab_ids = {}
    for column in result.get("colunas", {}).values():
        for tab in column.get("abas", []):
            old_tab_id = tab.get("id")
            next_id += 1
            tab["id"] = next_id
            tab_ids[old_tab_id] = next_id
            for section in tab.get("secoes", []):
                next_id += 1
                section["id"] = next_id
                for component in section.get("componentes", []):
                    next_id += 1
                    component["id"] = next_id
        if column.get("abaAtivaId") in tab_ids:
            column["abaAtivaId"] = tab_ids[column["abaAtivaId"]]
    return result


@login_required
@require_POST
def api_aplicar_template(request, id_ficha, template_id):
    sheet = CharacterSheet.objects.filter(pk=id_ficha, owner=request.user).first()
    template = SheetTemplate.objects.filter(pk=template_id, owner=request.user).first()
    if not sheet or not template:
        return JsonResponse({"erro": "Ficha ou template não encontrado."}, status=404)
    current_name, current_subtitle, avatar, visibility = (
        sheet.name,
        sheet.subtitle,
        sheet.avatar_path,
        sheet.visibility,
    )
    data = _renew_template_ids(template.structure)
    data.update(
        id=sheet.pk,
        nome=current_name,
        subtitulo=current_subtitle,
        avatar=avatar or None,
        visibilidade=visibility,
    )
    try:
        _save_sheet_payload(sheet, data)
    except ValueError as error:
        return JsonResponse({"erro": str(error)}, status=400)
    return JsonResponse(_sheet_payload(sheet))


@login_required
@require_http_methods(["DELETE"])
def api_deletar_template(request, id_ficha, template_id):
    if not CharacterSheet.objects.filter(pk=id_ficha, owner=request.user).exists():
        return JsonResponse({"erro": "Ficha não encontrada."}, status=404)
    template = SheetTemplate.objects.filter(pk=template_id, owner=request.user).first()
    if not template:
        return JsonResponse({"erro": "Template não encontrado."}, status=404)
    template.delete()
    return JsonResponse({"status": "success"})


@login_required
@require_POST
def api_criar_aba(request, id_ficha):
    sheet = CharacterSheet.objects.filter(pk=id_ficha, owner=request.user).first()
    if not sheet:
        return JsonResponse({"erro": "Ficha não encontrada."}, status=404)
    data = _sheet_payload(sheet)
    body = _json_body(request) or {}
    column_id = str(body.get("posicaoColuna", 1))
    column = data["colunas"].get(column_id)
    if not column:
        return JsonResponse({"erro": "Coluna não encontrada."}, status=404)
    if len(column["abas"]) >= 3:
        return JsonResponse({"erro": "Cada coluna pode conter no máximo três abas."}, status=400)
    tab_id = _next_structure_id(data)
    title = str(body.get("titulo") or "Nova Aba").strip()[:100] or "Nova Aba"
    tab = {"id": tab_id, "titulo": title, "secoes": []}
    column["abas"].append(tab)
    column["abaAtivaId"] = tab_id
    _save_sheet_payload(sheet, data)
    return JsonResponse({"status": "success", "aba": {"id": tab_id, "titulo": title}})


@login_required
@require_http_methods(["DELETE"])
def api_deletar_aba(request, id_ficha, aba_id):
    sheet = CharacterSheet.objects.filter(pk=id_ficha, owner=request.user).first()
    if not sheet:
        return JsonResponse({"erro": "Ficha não encontrada."}, status=404)
    data = _sheet_payload(sheet)
    for column in data["colunas"].values():
        for tab in list(column["abas"]):
            is_first_tab = column is data["colunas"]["1"] and tab is column["abas"][0]
            if str(tab.get("id")) == str(aba_id) and not is_first_tab:
                column["abas"].remove(tab)
                column["abaAtivaId"] = column["abas"][0]["id"] if column["abas"] else None
                _save_sheet_payload(sheet, data)
                return JsonResponse({"status": "success"})
    return JsonResponse({"erro": "Aba não encontrada."}, status=404)


@login_required
@require_POST
def api_criar_secao(request, id_ficha):
    sheet = CharacterSheet.objects.filter(pk=id_ficha, owner=request.user).first()
    if not sheet:
        return JsonResponse({"erro": "Ficha não encontrada."}, status=404)
    data = _sheet_payload(sheet)
    body = _json_body(request) or {}
    tab_id = body.get("abaId")
    tab = next(
        (
            tab
            for column in data["colunas"].values()
            for tab in column["abas"]
            if str(tab.get("id")) == str(tab_id)
        ),
        None,
    )
    if not tab:
        return JsonResponse({"erro": "Aba não encontrada."}, status=404)
    section_id = _next_structure_id(data)
    title = str(body.get("titulo") or "Nova Seção").strip()[:100] or "Nova Seção"
    section_type = str(body.get("tipo") or "AtributoSimples")
    tab["secoes"].append(
        {"id": section_id, "titulo": title, "tipo": section_type, "componentes": []}
    )
    _save_sheet_payload(sheet, data)
    return JsonResponse({"status": "success", "secao": {"id": section_id, "titulo": title}})


@login_required
@require_http_methods(["DELETE"])
def api_deletar_secao(request, id_ficha, secao_id):
    sheet = CharacterSheet.objects.filter(pk=id_ficha, owner=request.user).first()
    if not sheet:
        return JsonResponse({"erro": "Ficha não encontrada."}, status=404)
    data = _sheet_payload(sheet)
    for column in data["colunas"].values():
        for tab in column["abas"]:
            for section in list(tab["secoes"]):
                if str(section.get("id")) == str(secao_id):
                    tab["secoes"].remove(section)
                    _save_sheet_payload(sheet, data)
                    return JsonResponse({"status": "success"})
    return JsonResponse({"erro": "Seção não encontrada."}, status=404)


@login_required
@require_POST
def api_criar_componente(request, id_ficha):
    sheet = CharacterSheet.objects.filter(pk=id_ficha, owner=request.user).first()
    if not sheet:
        return JsonResponse({"erro": "Ficha não encontrada."}, status=404)
    data = _sheet_payload(sheet)
    body = _json_body(request) or {}
    section = _find_sheet_section(data, body.get("secaoId"))
    if section is None:
        return JsonResponse({"erro": "Seção não encontrada."}, status=404)
    component_type = str(body.get("tipo") or section.get("tipo") or "AtributoSimples")
    component = _default_component(component_type, body, _next_structure_id(data))
    if component is None:
        return JsonResponse({"erro": "Tipo de componente inválido."}, status=400)
    section["componentes"].append(component)
    _save_sheet_payload(sheet, data)
    return JsonResponse({"status": "success", "componente": component})


@login_required
@require_http_methods(["PUT"])
def api_atualizar_componente(request, id_ficha, comp_id):
    sheet = CharacterSheet.objects.filter(pk=id_ficha, owner=request.user).first()
    if not sheet:
        return JsonResponse({"erro": "Ficha não encontrada."}, status=404)
    data = _sheet_payload(sheet)
    body = _json_body(request)
    if body is None:
        return JsonResponse({"erro": "Dados JSON inválidos."}, status=400)
    allowed = {
        "rotulo", "valorAtual", "valorMaximo", "corSeletor", "estaMarcado", "campoTexto",
        "descricao", "nomeAtributo", "valorAtributo", "valorGrande", "valorPequeno",
        "valorBase", "valorBonus", "valorOutros", "subtituloAnotacao", "anotacaoExtra",
        "criterioOrdenacao",
    }
    for column in data["colunas"].values():
        for tab in column["abas"]:
            for section in tab["secoes"]:
                for component in section["componentes"]:
                    if str(component.get("id")) == str(comp_id):
                        component.update({key: value for key, value in body.items() if key in allowed})
                        _save_sheet_payload(sheet, data)
                        return JsonResponse({"status": "success", "componente": component})
    return JsonResponse({"erro": "Componente não encontrado."}, status=404)


@login_required
@require_http_methods(["DELETE"])
def api_deletar_componente(request, id_ficha, comp_id):
    sheet = CharacterSheet.objects.filter(pk=id_ficha, owner=request.user).first()
    if not sheet:
        return JsonResponse({"erro": "Ficha não encontrada."}, status=404)
    data = _sheet_payload(sheet)
    for column in data["colunas"].values():
        for tab in column["abas"]:
            for section in tab["secoes"]:
                for component in list(section["componentes"]):
                    if str(component.get("id")) == str(comp_id):
                        section["componentes"].remove(component)
                        _save_sheet_payload(sheet, data)
                        return JsonResponse({"status": "success"})
    return JsonResponse({"erro": "Componente não encontrado."}, status=404)


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_componente_item(request, id_ficha, comp_id):
    if request.method == "PUT":
        return api_atualizar_componente(request, id_ficha, comp_id)
    return api_deletar_componente(request, id_ficha, comp_id)


@login_required
@require_http_methods(["GET", "POST"])
def api_templates(request, id_ficha):
    if request.method == "GET":
        return api_listar_templates(request, id_ficha)
    return api_criar_template(request, id_ficha)


@login_required
@require_http_methods(["POST", "DELETE"])
def api_template_item(request, id_ficha, template_id):
    if request.method == "POST":
        return api_aplicar_template(request, id_ficha, template_id)
    return api_deletar_template(request, id_ficha, template_id)
