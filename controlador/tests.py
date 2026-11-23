from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from urllib.error import HTTPError

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from PIL import Image

from .fichas import validar_estrutura_ficha
from .campanhas import (
    LimiteCampanhaAtingido,
    criar_campanha,
    entrar_em_campanha,
    iniciar_sessao,
    parar_sessao,
)
from .models import (
    Arquivo,
    Campanha,
    CampanhaParticipante,
    Chave,
    FichaCampanha,
    FichaPersonagem,
    SessaoCampanha,
    TemplateFicha,
)
from .services import pode_criar_campanha, pode_criar_ficha, pode_participar_campanha
from .chatbot import GeminiIndisponivel, _chamar_gemini
from rpgvenv_django.storage import VersionedStaticFilesStorage


Usuario = get_user_model()


def valid_png():
    image = Image.new("RGB", (1, 1), color="purple")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class StaticAssetVersioningTests(SimpleTestCase):
    def test_static_url_changes_when_source_file_changes(self):
        with TemporaryDirectory() as directory:
            asset = Path(directory) / "probe.js"
            asset.write_text("first", encoding="utf-8")
            with override_settings(
                STATICFILES_DIRS=[directory],
                STATIC_URL="/static/",
            ):
                storage = VersionedStaticFilesStorage()
                first_url = storage.url("probe.js")
                asset.write_text("updated source", encoding="utf-8")
                second_url = storage.url("probe.js")

        self.assertRegex(first_url, r"^/static/probe\.js\?v=[0-9a-f]+-[0-9a-f]+$")
        self.assertNotEqual(first_url, second_url)


class GeminiApiTests(SimpleTestCase):
    @override_settings(
        GEMINI_API_KEY="test-private-key",
        GEMINI_MODEL="gemini-3.1-flash-lite",
    )
    def test_auth_and_quota_errors_are_reported_without_model_retries(self):
        erros = (
            (403, "PERMISSION_DENIED", "A chave de teste foi recusada"),
            (429, "RESOURCE_EXHAUSTED", "Cota indisponível"),
        )
        for codigo, status_api, mensagem_api in erros:
            with self.subTest(codigo=codigo):
                corpo_erro = json.dumps({
                    "error": {
                        "code": codigo,
                        "status": status_api,
                        "message": mensagem_api,
                    }
                }).encode("utf-8")
                erro = HTTPError(
                    "https://generativelanguage.googleapis.com/",
                    codigo,
                    "Erro de teste",
                    {},
                    BytesIO(corpo_erro),
                )
                with (
                    mock.patch(
                        "controlador.chatbot.urllib.request.urlopen",
                        side_effect=erro,
                    ) as urlopen,
                    self.assertLogs("controlador.chatbot", level="WARNING") as logs,
                ):
                    with self.assertRaises(GeminiIndisponivel) as resultado:
                        _chamar_gemini("prompt de teste")

                self.assertEqual(urlopen.call_count, 1)
                self.assertIn(str(codigo), str(resultado.exception))
                self.assertIn(status_api, str(resultado.exception))
                self.assertNotIn("test-private-key", "\n".join(logs.output))
                if codigo == 403:
                    self.assertIn("recusou a chave", str(resultado.exception))
                else:
                    self.assertIn("cota", str(resultado.exception))

    @override_settings(
        GEMINI_API_KEY="test-private-key",
        GEMINI_MODEL="modelo-inexistente",
    )
    def test_missing_model_tries_the_next_supported_model(self):
        erro_modelo = HTTPError(
            "https://generativelanguage.googleapis.com/",
            404,
            "Não encontrado",
            {},
            BytesIO(b'{"error":{"status":"NOT_FOUND","message":"Modelo ausente"}}'),
        )
        resposta = mock.MagicMock()
        resposta.__enter__.return_value.read.return_value = json.dumps({
            "candidates": [{
                "content": {"parts": [{"text": '{"mensagens": []}'}]}
            }]
        }).encode("utf-8")

        with mock.patch(
            "controlador.chatbot.urllib.request.urlopen",
            side_effect=[erro_modelo, resposta],
        ) as urlopen:
            resultado = _chamar_gemini("prompt de teste")

        self.assertEqual(resultado, {"mensagens": []})
        self.assertEqual(urlopen.call_count, 2)

    @override_settings(
        GEMINI_API_KEY="test-private-key",
        GEMINI_MODEL="gemini-3.1-flash-lite",
    )
    def test_unavailable_model_retries_once_then_uses_fallback(self):
        def erro_indisponivel():
            return HTTPError(
                "https://generativelanguage.googleapis.com/",
                503,
                "Indisponível",
                {},
                BytesIO(
                    b'{"error":{"status":"UNAVAILABLE",'
                    b'"message":"Alta demanda"}}'
                ),
            )

        resposta = mock.MagicMock()
        resposta.__enter__.return_value.read.return_value = json.dumps({
            "candidates": [{
                "content": {"parts": [{"text": '{"mensagens": []}'}]}
            }]
        }).encode("utf-8")

        with (
            mock.patch(
                "controlador.chatbot.urllib.request.urlopen",
                side_effect=[erro_indisponivel(), erro_indisponivel(), resposta],
            ) as urlopen,
            mock.patch("controlador.chatbot.time.sleep") as sleep,
        ):
            resultado = _chamar_gemini("prompt de teste")

        urls = [
            chamada.args[0].full_url
            for chamada in urlopen.call_args_list
        ]
        self.assertEqual(resultado, {"mensagens": []})
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(urls[0], urls[1])
        self.assertIn("gemini-3.5-flash-lite:generateContent", urls[2])
        sleep.assert_called_once()


class AccountFlowTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.addCleanup(self.media_directory.cleanup)

    def test_home_page_is_public(self):
        response = self.client.get(reverse("inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jogue qualquer RPG")
        self.assertNotContains(response, "TESTAR PALETA")

    def test_authenticated_home_page_has_no_palette_test_shortcut(self):
        user = Usuario.objects.create_user(
            email="palette@example.com",
            username="Paleta",
            password="SenhaForte-2098!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("inicio"))
        self.assertContains(response, reverse("perfil"))
        self.assertNotContains(response, "TESTAR PALETA")
        self.assertNotContains(response, "teste-paleta")

    def test_registration_creates_account_and_logs_user_in(self):
        response = self.client.post(
            reverse("cadastro"),
            {
                "username": "Jogadora",
                "email": "Pessoa@Example.com",
                "password1": "SenhaForte-2098!",
                "password2": "SenhaForte-2098!",
            },
        )

        user = Usuario.objects.get(email="pessoa@example.com")
        self.assertTrue(user.check_password("SenhaForte-2098!"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("perfil"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_registration_rejects_duplicate_email_case_insensitively(self):
        Usuario.objects.create_user(
            email="taken@example.com",
            username="Outro",
            password="SenhaForte-2098!",
        )

        response = self.client.post(
            reverse("cadastro"),
            {
                "username": "MaisUm",
                "email": "TAKEN@example.com",
                "password1": "SenhaForte-2098!",
                "password2": "SenhaForte-2098!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Usuario.objects.count(), 1)
        self.assertContains(response, "Já existe uma conta com este e-mail")

    def test_unknown_email_does_not_create_account_on_login(self):
        response = self.client.post(
            reverse("login"),
            {"username": "novo@example.com", "password": "senha-incorreta"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Usuario.objects.count(), 0)
        self.assertContains(response, "E-mail ou senha inválidos")

    def test_existing_user_can_log_in_with_email(self):
        user = Usuario.objects.create_user(
            email="login@example.com",
            username="Entrou",
            password="SenhaForte-2098!",
        )

        response = self.client.post(
            reverse("login"),
            {"username": "LOGIN@example.com", "password": "SenhaForte-2098!"},
        )

        self.assertRedirects(response, reverse("perfil"))
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_external_next_url_is_not_used_after_login(self):
        Usuario.objects.create_user(
            email="safe@example.com",
            username="Seguro",
            password="SenhaForte-2098!",
        )

        response = self.client.post(
            f"{reverse('login')}?next=https://example.org/",
            {"username": "safe@example.com", "password": "SenhaForte-2098!"},
        )

        self.assertRedirects(response, reverse("perfil"))

    def test_csrf_is_required_for_registration(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.get(reverse("cadastro"))

        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        response = csrf_client.post(
            reverse("cadastro"),
            {
                "username": "SemToken",
                "email": "csrf@example.com",
                "password1": "SenhaForte-2098!",
                "password2": "SenhaForte-2098!",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Usuario.objects.count(), 0)

    def test_profile_updates_username_and_email(self):
        user = Usuario.objects.create_user(
            email="old@example.com",
            username="NomeAntigo",
            password="SenhaForte-2098!",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("perfil"),
            {
                "acao": "perfil",
                "username": "NomeNovo",
                "email": "New@Example.com",
            },
        )

        user.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(user.username, "NomeNovo")
        self.assertEqual(user.email, "new@example.com")

    def test_profile_page_exposes_account_edit_controls(self):
        user = Usuario.objects.create_user(
            email="profile@example.com",
            username="Perfil",
            password="SenhaForte-2098!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("perfil"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'name="avatar"')
        self.assertContains(response, 'name="new_password1"')
        self.assertContains(response, 'name="old_password"')

    def test_profile_page_restores_three_legacy_content_tabs(self):
        user = Usuario.objects.create_user(
            email="profile-tabs@example.com",
            username="AbasPerfil",
            password="SenhaForte-2098!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("perfil"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Estamos em construção")
        self.assertContains(response, "Editar Informações de Perfil")
        self.assertContains(response, "Minhas Chaves de Acesso")
        self.assertContains(response, 'id="conteudo-editar"')
        self.assertContains(response, 'id="conteudo-chaves"')
        self.assertContains(response, 'name="new_password1"')
        self.assertNotContains(response, "HA4H4nF1tR1A0HA4")

    def test_profile_password_change_preserves_session(self):
        user = Usuario.objects.create_user(
            email="user@example.com",
            username="Jogador",
            password="SenhaAntiga-2098!",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("perfil"),
            {
                "acao": "senha",
                "old_password": "SenhaAntiga-2098!",
                "new_password1": "SenhaNova-2098!",
                "new_password2": "SenhaNova-2098!",
            },
        )

        user.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(user.check_password("SenhaNova-2098!"))
        self.assertEqual(self.client.get(reverse("perfil")).status_code, 200)

    def test_profile_accepts_valid_avatar(self):
        user = Usuario.objects.create_user(
            email="avatar@example.com",
            username="Avatar",
            password="SenhaForte-2098!",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("perfil"),
            {
                "acao": "perfil",
                "username": user.username,
                "email": user.email,
                "avatar": SimpleUploadedFile(
                    "foto.png",
                    valid_png(),
                    content_type="image/png",
                ),
            },
        )

        user.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(user.avatar.name.startswith("avatars/"))
        self.assertTrue(user.avatar.storage.exists(user.avatar.name))

    def test_profile_can_remove_existing_avatar(self):
        user = Usuario.objects.create_user(
            email="remove-avatar@example.com",
            username="AvatarRemovido",
            password="SenhaForte-2098!",
        )
        user.avatar.save("foto.png", ContentFile(valid_png()))
        avatar_storage = user.avatar.storage
        avatar_name = user.avatar.name
        self.client.force_login(user)

        response = self.client.post(
            reverse("perfil"),
            {
                "acao": "perfil",
                "username": user.username,
                "email": user.email,
                "remover_avatar": "on",
            },
        )

        user.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(user.avatar)
        self.assertFalse(avatar_storage.exists(avatar_name))

    def test_profile_rejects_non_image_uploaded_as_png(self):
        user = Usuario.objects.create_user(
            email="invalid-avatar@example.com",
            username="SemAvatar",
            password="SenhaForte-2098!",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("perfil"),
            {
                "acao": "perfil",
                "username": user.username,
                "email": user.email,
                "avatar": SimpleUploadedFile(
                    "fake.png",
                    b"not an image",
                    content_type="image/png",
                ),
            },
        )

        user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(user.avatar)
        self.assertIn("avatar", response.context["perfil_form"].errors)

    def test_profile_rejects_image_with_mismatched_extension(self):
        user = Usuario.objects.create_user(
            email="wrong-extension@example.com",
            username="FormatoIncorreto",
            password="SenhaForte-2098!",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("perfil"),
            {
                "acao": "perfil",
                "username": user.username,
                "email": user.email,
                "avatar": SimpleUploadedFile(
                    "foto.jpg",
                    valid_png(),
                    content_type="image/jpeg",
                ),
            },
        )

        user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(user.avatar)
        self.assertIn("avatar", response.context["perfil_form"].errors)

    def test_profile_rejects_duplicate_email_case_insensitively(self):
        Usuario.objects.create_user(
            email="taken@example.com",
            username="Outro",
            password="SenhaForte-2098!",
        )
        user = Usuario.objects.create_user(
            email="mine@example.com",
            username="Meu",
            password="SenhaForte-2098!",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("perfil"),
            {
                "acao": "perfil",
                "username": user.username,
                "email": "TAKEN@example.com",
            },
        )

        user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.email, "mine@example.com")
        self.assertContains(response, "Já existe uma conta com este e-mail")

    def test_unauthenticated_placeholder_redirects_to_login(self):
        response = self.client.get(reverse("colecoes"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('colecoes')}",
        )

    def test_authenticated_unimplemented_route_returns_empty_page(self):
        user = Usuario.objects.create_user(
            email="user@example.com",
            username="Jogador",
            password="SenhaForte-2098!",
        )
        self.client.force_login(user)

        response = self.client.get("/uma-area-ainda-nao-implementada/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    def test_logout_requires_post(self):
        user = Usuario.objects.create_user(
            email="user@example.com",
            username="Jogador",
            password="SenhaForte-2098!",
        )
        self.client.force_login(user)

        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("inicio"))
        self.assertNotIn("_auth_user_id", self.client.session)


class FileLibraryTests(TestCase):
    pdf_content = b"%PDF-1.4\n1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n"

    def setUp(self):
        self.media_directory = TemporaryDirectory()
        media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.user = Usuario.objects.create_user(
            email="library@example.com",
            username="Biblioteca",
            password="SenhaForte-2098!",
        )
        self.client.force_login(self.user)

    def upload(self, name, content, content_type):
        return self.client.post(
            reverse("livros"),
            {
                "arquivo": SimpleUploadedFile(
                    name,
                    content,
                    content_type=content_type,
                )
            },
        )

    def test_library_page_shows_two_categories_search_and_viewer_controls(self):
        response = self.client.get(reverse("livros"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Documentos")
        self.assertContains(response, "Handouts")
        self.assertContains(response, '<select id="filtro_arquivo"')
        self.assertContains(response, 'value="documento"')
        self.assertContains(response, 'value="handout"')
        self.assertContains(response, 'id="campo_busca"')
        self.assertContains(response, 'id="zoom_in"')
        self.assertContains(response, 'id="zoom_out"')
        self.assertContains(response, "biblioteca.js")

    def test_library_renders_original_filename_in_the_file_list(self):
        self.upload("Livro de regras.pdf", self.pdf_content, "application/pdf")

        response = self.client.get(reverse("livros"))

        self.assertContains(response, "Livro de regras.pdf")
        self.assertNotContains(response, "{{ arquivo.nome_original }}")

    def test_upload_pdf_is_owned_and_stored_outside_static_files(self):
        response = self.upload("Livro de regras.pdf", self.pdf_content, "application/pdf")

        arquivo = Arquivo.objects.get(usuario=self.user)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(arquivo.tipo, Arquivo.Tipo.DOCUMENTO)
        self.assertEqual(arquivo.nome_original, "Livro de regras.pdf")
        self.assertTrue(arquivo.arquivo.name.startswith(f"biblioteca/{self.user.pk}/"))
        self.assertTrue(arquivo.arquivo.storage.exists(arquivo.arquivo.name))

    def test_upload_image_and_preview_returns_inline_image_content(self):
        uploaded = SimpleUploadedFile(
            "mapa.png",
            valid_png(),
            content_type="image/png",
        )
        response = self.client.post(reverse("livros"), {"arquivo": uploaded})

        arquivo = Arquivo.objects.get(usuario=self.user)
        preview = self.client.get(
            reverse("visualizar_arquivo", args=(arquivo.pk,))
        )
        content = b"".join(preview.streaming_content)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(arquivo.tipo, Arquivo.Tipo.HANDOUT)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview["Content-Type"], "image/png")
        self.assertIn("inline", preview["Content-Disposition"])
        self.assertEqual(content, valid_png())
        self.assertEqual(preview["Cache-Control"], "private, no-store")

    def test_pdf_preview_supports_byte_range_requests(self):
        self.upload("Livro.pdf", self.pdf_content, "application/pdf")
        arquivo = Arquivo.objects.get(usuario=self.user)

        response = self.client.get(
            reverse("visualizar_arquivo", args=(arquivo.pk,)),
            HTTP_RANGE="bytes=0-4",
        )

        content = b"".join(response.streaming_content)
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], f"bytes 0-4/{len(self.pdf_content)}")
        self.assertEqual(response["Accept-Ranges"], "bytes")
        self.assertEqual(content, b"%PDF-")

    def test_unsatisfiable_range_returns_416(self):
        self.upload("Livro.pdf", self.pdf_content, "application/pdf")
        arquivo = Arquivo.objects.get(usuario=self.user)

        response = self.client.get(
            reverse("visualizar_arquivo", args=(arquivo.pk,)),
            HTTP_RANGE=f"bytes={len(self.pdf_content)}-",
        )

        self.assertEqual(response.status_code, 416)
        self.assertEqual(response["Content-Range"], f"bytes */{len(self.pdf_content)}")

    def test_invalid_pdf_signature_is_rejected(self):
        response = self.upload("arquivo.pdf", b"texto comum", "application/pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Arquivo.objects.count(), 0)
        self.assertIn("arquivo", response.context["form"].errors)

    def test_image_with_mismatched_extension_is_rejected(self):
        uploaded = SimpleUploadedFile(
            "mapa.jpg",
            valid_png(),
            content_type="image/jpeg",
        )

        response = self.client.post(reverse("livros"), {"arquivo": uploaded})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Arquivo.objects.count(), 0)
        self.assertIn("arquivo", response.context["form"].errors)

    def test_unsupported_text_document_is_rejected(self):
        response = self.upload("notas.txt", b"texto", "text/plain")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Arquivo.objects.count(), 0)
        self.assertIn("arquivo", response.context["form"].errors)

    def test_upload_larger_than_16_mib_is_rejected(self):
        response = self.upload(
            "grande.pdf",
            b"%PDF-" + (b"x" * (16 * 1024 * 1024)) + b"%%EOF",
            "application/pdf",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Arquivo.objects.count(), 0)
        self.assertIn("arquivo", response.context["form"].errors)

    def test_other_user_cannot_list_preview_or_delete_file(self):
        self.upload("Livro.pdf", self.pdf_content, "application/pdf")
        arquivo = Arquivo.objects.get(usuario=self.user)
        other_user = Usuario.objects.create_user(
            email="other@example.com",
            username="Outro",
            password="SenhaForte-2098!",
        )
        self.client.force_login(other_user)

        listing = self.client.get(reverse("livros"))
        preview = self.client.get(
            reverse("visualizar_arquivo", args=(arquivo.pk,))
        )
        deletion = self.client.post(
            reverse("remover_arquivo", args=(arquivo.pk,))
        )

        self.assertEqual(listing.status_code, 200)
        self.assertNotContains(listing, "Livro.pdf")
        self.assertEqual(preview.status_code, 404)
        self.assertEqual(deletion.status_code, 404)
        self.assertTrue(arquivo.arquivo.storage.exists(arquivo.arquivo.name))
        self.assertTrue(Arquivo.objects.filter(pk=arquivo.pk).exists())

    def test_owner_can_delete_file_and_storage_object(self):
        self.upload("Livro.pdf", self.pdf_content, "application/pdf")
        arquivo = Arquivo.objects.get(usuario=self.user)
        stored_name = arquivo.arquivo.name
        storage = arquivo.arquivo.storage

        response = self.client.post(
            reverse("remover_arquivo", args=(arquivo.pk,))
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Arquivo.objects.filter(pk=arquivo.pk).exists())
        self.assertFalse(storage.exists(stored_name))

    def test_unauthenticated_library_redirects_to_login(self):
        self.client.logout()

        response = self.client.get(reverse("livros"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('livros')}",
        )

    def test_avatar_endpoint_requires_authentication_and_serves_own_image(self):
        image_bytes = valid_png()
        self.user.avatar.save(
            "profile.png",
            SimpleUploadedFile("profile.png", image_bytes, content_type="image/png"),
            save=True,
        )

        response = self.client.get(reverse("avatar_proprio"))
        content = b"".join(response.streaming_content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(content, image_bytes)

        self.client.logout()
        anonymous_response = self.client.get(reverse("avatar_proprio"))
        self.assertRedirects(
            anonymous_response,
            f"{reverse('login')}?next={reverse('avatar_proprio')}",
        )


class ExpansionKeyTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(
            email="keys@example.com",
            username="ChaveUser",
            password="SenhaForte-2098!",
        )
        self.client.force_login(self.user)

    def test_purchase_generates_key_and_shows_nominal_email_notification(self):
        response = self.client.post(
            reverse("comprar_chave"),
            {"pacote": "1", "next": reverse("perfil")},
            follow=True,
        )

        chave = Chave.objects.get(usuario=self.user)
        self.assertRedirects(response, f"{reverse('perfil')}?aba=chaves&loja=1")
        self.assertRegex(chave.codigo, r"^[A-Z0-9]{4}(?:-[A-Z0-9]{4}){2}-[A-Z0-9]{3}$")
        self.assertFalse(chave.foi_usada)
        self.assertContains(response, "A chave foi enviada para o seu perfil.")

    def test_purchase_retries_when_generated_code_collides(self):
        Chave.objects.create(
            codigo="AB12-CD34-EF56-GH7",
            usuario=self.user,
        )
        with mock.patch(
            "controlador.services._novo_codigo",
            side_effect=["AB12-CD34-EF56-GH7", "JK89-LM01-NP23-QR4"],
        ):
            response = self.client.post(
                reverse("comprar_chave"),
                {"pacote": "1", "next": reverse("perfil")},
            )

        self.assertRedirects(response, f"{reverse('perfil')}?aba=chaves&loja=1")
        self.assertEqual(Chave.objects.count(), 2)
        self.assertTrue(Chave.objects.filter(pk="JK89-LM01-NP23-QR4").exists())

    def test_unavailable_packages_cannot_be_purchased_by_tampering_with_request(self):
        response = self.client.post(
            reverse("comprar_chave"),
            {"pacote": "5", "next": reverse("perfil")},
            follow=True,
        )

        self.assertEqual(Chave.objects.count(), 0)
        self.assertContains(response, "O pacote selecionado não está disponível.")

    def test_redemption_activates_unlimited_access_and_records_usage(self):
        chave = Chave.objects.create(
            codigo="AB12-CD34-EF56-GH7",
            usuario=self.user,
        )

        response = self.client.post(
            reverse("resgatar_chave"),
            {
                "codigo": chave.codigo.lower(),
                "next": reverse("perfil"),
            },
        )

        self.user.refresh_from_db()
        chave.refresh_from_db()
        self.assertRedirects(response, f"{reverse('perfil')}?aba=chaves&loja=1")
        self.assertTrue(self.user.tem_chave)
        self.assertTrue(chave.foi_usada)
        self.assertIsNotNone(chave.resgatada_em)

    def test_key_cannot_be_redeemed_by_another_user_or_reused(self):
        chave = Chave.objects.create(
            codigo="AB12-CD34-EF56-GH7",
            usuario=self.user,
        )
        other_user = Usuario.objects.create_user(
            email="other-keys@example.com",
            username="OutraConta",
            password="SenhaForte-2098!",
        )
        self.client.force_login(other_user)
        other_response = self.client.post(
            reverse("resgatar_chave"),
            {"codigo": chave.codigo, "next": reverse("perfil")},
            follow=True,
        )
        self.assertFalse(Chave.objects.get(pk=chave.pk).foi_usada)
        self.assertFalse(Usuario.objects.get(pk=other_user.pk).tem_chave)
        self.assertContains(
            other_response,
            "Chave inválida, já resgatada ou vinculada a outra conta.",
        )

        self.client.force_login(self.user)
        first_response = self.client.post(
            reverse("resgatar_chave"),
            {"codigo": chave.codigo, "next": reverse("perfil")},
        )
        second_response = self.client.post(
            reverse("resgatar_chave"),
            {"codigo": chave.codigo, "next": reverse("perfil")},
            follow=True,
        )
        self.assertRedirects(
            first_response,
            f"{reverse('perfil')}?aba=chaves&loja=1",
        )
        self.assertContains(
            second_response,
            "Chave inválida, já resgatada ou vinculada a outra conta.",
        )

    def test_invalid_key_format_is_rejected(self):
        response = self.client.post(
            reverse("resgatar_chave"),
            {"codigo": "nao-e-uma-chave", "next": reverse("perfil")},
            follow=True,
        )

        self.assertEqual(Chave.objects.count(), 0)
        self.assertFalse(Usuario.objects.get(pk=self.user.pk).tem_chave)
        self.assertContains(response, "Informe uma chave no formato")

    def test_profile_lists_purchased_and_redeemed_key(self):
        chave = Chave.objects.create(
            codigo="AB12-CD34-EF56-GH7",
            usuario=self.user,
            foi_usada=True,
        )

        response = self.client.get(f"{reverse('perfil')}?aba=chaves")

        self.assertContains(response, chave.codigo)
        self.assertContains(response, "Resgatada")
        self.assertContains(response, "Minhas Chaves de Acesso")

    def test_collections_displays_basic_and_unlimited_access_status(self):
        response = self.client.get(reverse("colecoes"))
        self.assertContains(response, "Plano básico")
        self.assertContains(response, "Até uma ficha ativa por vez.")
        self.assertContains(response, "Criação de campanhas indisponível.")

        self.user.tem_chave = True
        self.user.save(update_fields=["tem_chave"])
        response = self.client.get(reverse("colecoes"))
        self.assertContains(response, "Acesso ilimitado ativo")

    def test_authenticated_pages_show_the_key_store_and_all_package_options(self):
        for url in (
            reverse("inicio"),
            reverse("perfil"),
            reverse("livros"),
            reverse("colecoes"),
        ):
            response = self.client.get(url)
            self.assertContains(response, "Receba acesso ilimitado")
            self.assertContains(response, "Adquirir chaves")
            self.assertContains(response, "5 chaves")
            self.assertContains(response, "10 chaves")
            self.assertContains(response, "Resgatar")

        self.assertContains(response, "Em breve")

    def test_basic_and_keyed_accounts_obey_expansion_limits(self):
        self.assertTrue(pode_criar_ficha(self.user, fichas_ativas=0))
        self.assertFalse(pode_criar_ficha(self.user, fichas_ativas=1))
        self.assertTrue(pode_participar_campanha(self.user, campanhas_ativas=0))
        self.assertFalse(pode_participar_campanha(self.user, campanhas_ativas=1))
        self.assertFalse(pode_criar_campanha(self.user))

        self.user.tem_chave = True
        self.user.save(update_fields=["tem_chave"])
        self.assertTrue(pode_criar_ficha(self.user, fichas_ativas=10))
        self.assertTrue(pode_participar_campanha(self.user, campanhas_ativas=10))
        self.assertTrue(pode_criar_campanha(self.user))

    def test_purchase_and_redemption_require_authentication_and_post(self):
        self.client.logout()
        response = self.client.get(reverse("comprar_chave"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.post(reverse("resgatar_chave")).status_code, 302)


class CharacterSheetTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(
            email="fichas@example.com",
            username="Fichas",
            password="SenhaForte-2098!",
        )
        self.client.force_login(self.user)
        self.ficha = FichaPersonagem.objects.create(
            usuario=self.user,
            nome="Personagem",
            aspecto="Explorador",
        )

    def test_character_management_uses_renamed_template(self):
        response = self.client.get(reverse("personagens"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "gerenciar_fichas.html")

    def test_editor_renders_optional_evidence_control(self):
        response = self.client.get(reverse("criador", args=[self.ficha.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="chk_evidenciar"')
        self.assertContains(response, 'id="painel_opcoes_evidenciar"')
        self.assertRegex(
            response.content.decode(),
            r'/static/js/criador-componentes\.js\?v=[0-9a-f]+-[0-9a-f]+',
        )

    def test_basic_account_can_create_only_one_sheet(self):
        response = self.client.post(
            reverse("criar_ficha"),
            {"nome_personagem": "Outra ficha", "subtitulo": "Aspecto"},
        )

        self.assertRedirects(response, reverse("personagens"))
        self.assertEqual(FichaPersonagem.objects.filter(usuario=self.user).count(), 1)

    def test_json_save_persists_sheet_and_enforces_ownership(self):
        payload = {
            "id": self.ficha.pk,
            "nome": "Ficha atualizada",
            "subtitulo": "Nova história",
            **self.ficha.estrutura_json,
        }
        response = self.client.post(
            reverse("api_ficha", args=[self.ficha.pk]),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.nome, "Ficha atualizada")
        self.assertEqual(self.ficha.aspecto, "Nova história")

        outro_usuario = Usuario.objects.create_user(
            email="outro@example.com",
            username="Outro",
            password="SenhaForte-2098!",
        )
        self.client.force_login(outro_usuario)
        response = self.client.get(reverse("api_ficha", args=[self.ficha.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["erro"], "O recurso solicitado não foi encontrado.")

    def test_template_creation_and_application_preserve_identity_and_renew_ids(self):
        create_response = self.client.post(
            reverse("api_templates_ficha", args=[self.ficha.pk]),
            data=json.dumps({"nome": "Modelo"}),
            content_type="application/json",
        )

        self.assertEqual(create_response.status_code, 201)
        template = TemplateFicha.objects.get(usuario=self.user, nome="Modelo")

        self.ficha.nome = "Alterada"
        self.ficha.save(update_fields=["nome"])
        apply_response = self.client.post(
            reverse(
                "api_aplicar_template_ficha",
                args=[self.ficha.pk, template.pk],
            )
        )

        self.assertEqual(apply_response.status_code, 200)
        self.ficha.refresh_from_db()
        self.assertEqual(self.ficha.nome, "Alterada")
        abas_modelo = template.estrutura_json["colunas"]["1"]["abas"]
        abas_aplicadas = apply_response.json()["colunas"]["1"]["abas"]
        self.assertEqual(
            [aba["titulo"] for aba in abas_aplicadas],
            [aba["titulo"] for aba in abas_modelo],
        )
        self.assertNotEqual(abas_aplicadas[0]["id"], abas_modelo[0]["id"])

    def test_unauthenticated_sheet_api_returns_json_401(self):
        self.client.logout()

        response = self.client.get(reverse("api_ficha", args=[self.ficha.pk]))

        self.assertEqual(response.status_code, 401)
        self.assertIn("application/json", response["Content-Type"])

    def test_sheet_api_requires_csrf_for_json_mutations(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        csrf_client.get(reverse("criador", args=[self.ficha.pk]))
        payload = {
            "id": self.ficha.pk,
            "nome": self.ficha.nome,
            "subtitulo": self.ficha.aspecto,
            **self.ficha.estrutura_json,
        }
        url = reverse("api_ficha", args=[self.ficha.pk])

        rejected = csrf_client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 403)

        accepted = csrf_client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_client.cookies["csrftoken"].value,
        )
        self.assertEqual(accepted.status_code, 200)


class CharacterSheetStructureTests(TestCase):
    def test_three_tabs_designate_existing_tab_as_default_without_exceeding_limit(self):
        estrutura = {
            "colunas": {
                "1": {
                    "abas": [
                        {"id": 1, "titulo": "Ficha", "secoes": []},
                        {"id": 2, "titulo": "Combate", "secoes": []},
                        {"id": 3, "titulo": "Inventário", "secoes": []},
                    ]
                }
            }
        }

        normalizada = validar_estrutura_ficha(estrutura)
        abas = normalizada["colunas"]["1"]["abas"]

        self.assertEqual(len(abas), 3)
        self.assertTrue(abas[0]["ehPadrao"])


class CampaignTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.addCleanup(self.media_directory.cleanup)

        self.mestre = Usuario.objects.create_user(
            email="mestre@example.com",
            username="Mestre",
            password="SenhaForte-2098!",
            tem_chave=True,
        )
        self.jogador = Usuario.objects.create_user(
            email="jogador@example.com",
            username="Jogador",
            password="SenhaForte-2098!",
        )
        self.espectador = Usuario.objects.create_user(
            email="espectador@example.com",
            username="Espectador",
            password="SenhaForte-2098!",
        )
        self.campanha = criar_campanha(self.mestre, "Campanha de teste")

    def test_session_history_is_a_master_only_modal_next_to_session_control(self):
        self.client.force_login(self.mestre)
        response = self.client.get(reverse("campanha", args=[self.campanha.pk]))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="botao-historico-sessoes"', html)
        self.assertIn('id="modal-historico-sessoes"', html)
        self.assertLess(
            html.index('id="botao-historico-sessoes"'),
            html.index('id="botao-iniciar-sessao"'),
        )
        self.assertIn("Nenhuma sessão registrada.", html)

        entrar_em_campanha(self.jogador, self.campanha.codigo_convite)
        self.client.force_login(self.jogador)
        response = self.client.get(reverse("campanha", args=[self.campanha.pk]))
        self.assertNotContains(response, 'id="botao-historico-sessoes"')
        self.assertNotContains(response, 'id="modal-historico-sessoes"')

    def test_campaign_creation_form_is_a_modal_on_management_page(self):
        self.client.force_login(self.mestre)
        response = self.client.get(reverse("campanhas"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "gerenciar_campanha.html")
        self.assertContains(response, 'id="modal_criar_campanha"')
        self.assertContains(response, "abrirModalCriarCampanha()")
        self.assertContains(
            response,
            'id="modal_criar_campanha" class="hidden fixed inset-0',
        )

        response = self.client.post(
            reverse("criar_campanha"),
            {"titulo": "", "descricao": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "gerenciar_campanha.html")
        self.assertContains(response, "Este campo é obrigatório.")
        self.assertContains(
            response,
            'id="modal_criar_campanha" class="fixed inset-0',
        )

    def test_old_campaign_creation_page_redirects_to_manager(self):
        self.client.force_login(self.mestre)

        self.assertRedirects(
            self.client.get(reverse("criar_campanha")),
            reverse("campanhas"),
        )

    def test_basic_account_can_join_only_one_campaign(self):
        outra = criar_campanha(self.mestre, "Outra campanha")

        entrou, criado = entrar_em_campanha(
            self.jogador,
            self.campanha.codigo_convite,
        )
        self.assertTrue(criado)
        self.assertEqual(entrou, self.campanha)

        with self.assertRaises(LimiteCampanhaAtingido):
            entrar_em_campanha(self.jogador, outra.codigo_convite)

        self.jogador.tem_chave = True
        self.jogador.save(update_fields=["tem_chave"])
        entrar_em_campanha(self.jogador, outra.codigo_convite)
        self.assertEqual(
            CampanhaParticipante.objects.filter(usuario=self.jogador).count(),
            2,
        )

    def test_basic_user_cannot_create_campaign_and_invalid_code_is_reported(self):
        self.client.force_login(self.jogador)
        response = self.client.post(
            reverse("criar_campanha"),
            {"titulo": "Sem permissão", "descricao": ""},
            follow=True,
        )

        self.assertContains(response, "A criação de campanhas exige acesso ilimitado.")
        self.assertEqual(Campanha.objects.count(), 1)

        response = self.client.post(
            reverse("entrar_campanha"),
            {"codigo_campanha": "ABC-123-45"},
            follow=True,
        )
        self.assertContains(response, "Campanha não encontrada para este código.")

    def test_keyed_user_can_create_campaign_and_copy_duplicate_template_name(self):
        self.client.force_login(self.mestre)
        response = self.client.post(
            reverse("criar_campanha"),
            {"titulo": "Campanha nova", "descricao": "Descrição"},
        )
        self.assertEqual(response.status_code, 302)
        criada = Campanha.objects.get(titulo="Campanha nova")
        self.assertEqual(criada.mestre, self.mestre)
        self.assertEqual(criada.codigo_convite.count("-"), 2)

        entrar_em_campanha(self.jogador, self.campanha.codigo_convite)
        template_mestre = TemplateFicha.objects.create(
            usuario=self.mestre,
            nome="Template compartilhado",
            estrutura_json={},
        )
        self.campanha.template_mestre = template_mestre
        self.campanha.save(update_fields=["template_mestre"])
        TemplateFicha.objects.create(
            usuario=self.jogador,
            nome=template_mestre.nome,
            estrutura_json={"meu": "template"},
        )

        self.client.force_login(self.jogador)
        response = self.client.post(
            reverse("copiar_template_campanha", args=[self.campanha.pk]),
            follow=True,
        )
        self.assertContains(response, "Template copiado para sua conta.")
        self.assertEqual(
            TemplateFicha.objects.filter(
                usuario=self.jogador,
                nome=template_mestre.nome,
            ).count(),
            2,
        )

    def test_session_snapshot_excludes_online_spectators_and_records_history(self):
        entrar_em_campanha(self.jogador, self.campanha.codigo_convite)
        entrar_em_campanha(self.espectador, self.campanha.codigo_convite)
        jogador_extra = Usuario.objects.create_user(
            email="jogador-extra@example.com",
            username="JogadorExtra",
            password="SenhaForte-2098!",
        )
        entrar_em_campanha(jogador_extra, self.campanha.codigo_convite)
        ficha = FichaPersonagem.objects.create(
            usuario=self.jogador,
            nome="Aventureiro",
            aspecto="Corajoso",
        )
        FichaCampanha.objects.create(campanha=self.campanha, ficha=ficha)
        ficha_extra = FichaPersonagem.objects.create(
            usuario=jogador_extra,
            nome="Exploradora",
            aspecto="Curiosa",
        )
        FichaCampanha.objects.create(campanha=self.campanha, ficha=ficha_extra)

        with CaptureQueriesContext(connection) as queries:
            sessao = iniciar_sessao(self.campanha)
        presentes = {item["usuario_id"] for item in sessao.participantes_json}
        self.assertEqual(
            presentes,
            {self.mestre.pk, self.jogador.pk, jogador_extra.pk},
        )
        ficha_queries = [
            query
            for query in queries.captured_queries
            if "controlador_fichacampanha" in query["sql"].lower()
        ]
        self.assertEqual(len(ficha_queries), 1)
        self.assertFalse(SessaoCampanha.objects.get(pk=sessao.pk).encerrada_em)

        self.client.force_login(self.mestre)
        self.assertEqual(
            self.client.post(
                reverse("parar_sessao_campanha", args=[self.campanha.pk])
            ).status_code,
            200,
        )
        sessao.refresh_from_db()
        self.assertIsNotNone(sessao.encerrada_em)
        self.assertGreaterEqual(sessao.duracao_segundos, 0)
        self.assertContains(
            self.client.get(reverse("campanha", args=[self.campanha.pk])),
            "Histórico de sessões",
        )

    def test_chatbot_interprets_absent_character_and_persists_context(self):
        ficha = FichaPersonagem.objects.create(
            usuario=self.jogador,
            nome="Aventureiro",
            aspecto="Corajoso",
            estrutura_json={"visibilidade": "todos", "colunas": {}},
        )
        FichaCampanha.objects.create(campanha=self.campanha, ficha=ficha)
        sessao = iniciar_sessao(self.campanha)

        resposta_gemini = {
            "mensagens": [{
                "personagem": "Aventureiro",
                "texto": "Seguro a lanterna e investigo a porta.",
                "rolagens": [{
                    "teste": "Percepção",
                    "quantidade": 1,
                    "dados": 20,
                    "dificuldade": 10,
                    "explosao": False,
                }],
            }]
        }
        self.client.force_login(self.mestre)
        with mock.patch(
            "controlador.chatbot._chamar_gemini",
            return_value=resposta_gemini,
        ):
            response = self.client.post(
                reverse("api_chatbot_campanha", args=[self.campanha.pk]),
                data=json.dumps({"comando": "Role percepção e investigue a porta"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        dados = response.json()
        self.assertEqual(dados["mensagens"][0]["personagem"], "Aventureiro")
        self.assertEqual(dados["mensagens"][0]["rolagens"][0]["dados"], 20)
        sessao.refresh_from_db()
        self.assertEqual(len(sessao.chatbot_json["mensagens"]), 2)

    def test_chatbot_handles_multiple_absent_characters_without_crossing_stats(self):
        jogador_extra = Usuario.objects.create_user(
            email="offline-extra@example.com",
            username="JogadorExtra",
            password="SenhaForte-2098!",
        )
        entrar_em_campanha(jogador_extra, self.campanha.codigo_convite)
        CampanhaParticipante.objects.filter(
            campanha=self.campanha,
            usuario=jogador_extra,
        ).update(ultimo_acesso=None)
        ficha_um = FichaPersonagem.objects.create(
            usuario=self.jogador,
            nome="Ana",
            aspecto="Investigadora",
            estrutura_json={
                "visibilidade": "todos",
                "colunas": {
                    "1": {
                        "abas": [{
                            "titulo": "Geral",
                            "ehPadrao": True,
                            "secoes": [{
                                "titulo": "Vitalidade",
                                "tipo": "AtributoDuplo",
                                "componentes": [{
                                    "rotulo": "Vida",
                                    "valorAtual": 12,
                                    "valorMaximo": 20,
                                }],
                            }],
                        }]
                    }
                },
            },
        )
        ficha_dois = FichaPersonagem.objects.create(
            usuario=jogador_extra,
            nome="Beto",
            aspecto="Guarda",
            estrutura_json={
                "visibilidade": "todos",
                "colunas": {
                    "1": {
                        "abas": [{
                            "titulo": "Geral",
                            "ehPadrao": True,
                            "secoes": [{
                                "titulo": "Vitalidade",
                                "tipo": "AtributoDuplo",
                                "componentes": [{
                                    "rotulo": "Vida",
                                    "valorAtual": 30,
                                    "valorMaximo": 30,
                                }],
                            }],
                        }]
                    }
                },
            },
        )
        FichaCampanha.objects.create(campanha=self.campanha, ficha=ficha_um)
        FichaCampanha.objects.create(campanha=self.campanha, ficha=ficha_dois)
        sessao = iniciar_sessao(self.campanha)

        resposta_gemini = {
            "mensagens": [
                {
                    "personagem": "Ana",
                    "texto": "Ana permanece com 12/20 PV.",
                    "rolagens": [],
                },
                {
                    "personagem": "Beto",
                    "texto": "Beto permanece com 30/30 PV.",
                    "rolagens": [],
                },
            ]
        }
        self.client.force_login(self.mestre)
        with mock.patch(
            "controlador.chatbot._chamar_gemini",
            return_value=resposta_gemini,
        ):
            response = self.client.post(
                reverse("api_chatbot_campanha", args=[self.campanha.pk]),
                data=json.dumps({"comando": "Mantenham suas posições"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        nomes = [item["personagem"] for item in response.json()["mensagens"]]
        self.assertEqual(nomes, ["Ana", "Beto"])
        self.assertEqual(
            set(response.json()["faltosos"]),
            {"Ana", "Beto"},
        )
        sessao.refresh_from_db()
        self.assertEqual(len(sessao.chatbot_json["mensagens"]), 3)

    def test_chatbot_only_rolls_when_explicitly_requested_and_mixes_different_dice(self):
        ficha = FichaPersonagem.objects.create(
            usuario=self.jogador,
            nome="Aventureiro",
            aspecto="Corajoso",
        )
        FichaCampanha.objects.create(campanha=self.campanha, ficha=ficha)
        iniciar_sessao(self.campanha)
        self.client.force_login(self.mestre)

        with mock.patch(
            "controlador.chatbot._chamar_gemini",
            return_value={
                "mensagens": [{
                    "personagem": "Aventureiro",
                    "texto": "Mantenho a posição.",
                    "rolagens": [{
                        "teste": "Percepção",
                        "dados": 20,
                        "quantidade": 1,
                    }],
                }]
            },
        ):
            resposta_sem_pedido = self.client.post(
                reverse("api_chatbot_campanha", args=[self.campanha.pk]),
                data=json.dumps({"comando": "Observe a porta e permaneça em silêncio"}),
                content_type="application/json",
            )
        self.assertEqual(resposta_sem_pedido.json()["mensagens"][0]["rolagens"], [])
        self.assertNotIn("d20", resposta_sem_pedido.json()["mensagens"][0]["texto"])

        with mock.patch(
            "controlador.chatbot._chamar_gemini",
            return_value={
                "mensagens": [{
                    "personagem": "Aventureiro",
                    "texto": "Faço os dois testes.",
                    "rolagens": [
                        {"teste": "Percepção", "dados": 20, "quantidade": 1, "dificuldade": 12},
                        {"teste": "Dano", "dados": 6, "quantidade": 2, "explosao": True},
                    ],
                }]
            },
        ):
            resposta_com_testes = self.client.post(
                reverse("api_chatbot_campanha", args=[self.campanha.pk]),
                data=json.dumps({
                    "comando": "Role um teste de percepção em d20 e role 2d6 de dano"
                }),
                content_type="application/json",
            )

        mensagem = resposta_com_testes.json()["mensagens"][0]
        self.assertEqual(len(mensagem["rolagens"]), 2)
        self.assertIn("Percepção — d20", mensagem["texto"])
        self.assertIn("Dano — d6", mensagem["texto"])
        self.assertNotIn("mt-2 rounded-lg", mensagem["texto"])

    def test_chatbot_can_leave_character_when_requested(self):
        ficha = FichaPersonagem.objects.create(
            usuario=self.jogador,
            nome="Aventureiro",
            aspecto="Corajoso",
        )
        FichaCampanha.objects.create(campanha=self.campanha, ficha=ficha)
        iniciar_sessao(self.campanha)
        self.client.force_login(self.mestre)

        with mock.patch(
            "controlador.chatbot._chamar_gemini",
            return_value={
                "mensagens": [{
                    "personagem": "Aventureiro",
                    "texto": "A ação não exige teste; explico a regra fora da cena.",
                }]
            },
        ):
            response = self.client.post(
                reverse("api_chatbot_campanha", args=[self.campanha.pk]),
                data=json.dumps({
                    "comando": "Saia do personagem e explique a regra dessa ação"
                }),
                content_type="application/json",
            )

        self.assertEqual(response.json()["mensagens"][0]["personagem"], "Narrador")
        self.assertEqual(response.json()["mensagens"][0]["rolagens"], [])

    def test_chatbot_rejects_unknown_character_and_invalid_roll_parameters(self):
        ficha = FichaPersonagem.objects.create(
            usuario=self.jogador,
            nome="Aventureiro",
            aspecto="Corajoso",
        )
        FichaCampanha.objects.create(campanha=self.campanha, ficha=ficha)
        iniciar_sessao(self.campanha)

        resposta_gemini = {
            "mensagens": [{
                "personagem": "PersonagemInventado",
                "texto": "Executa uma ação.",
                "rolagens": [{
                    "teste": "Teste inválido",
                    "quantidade": "muita",
                    "dados": "muitos",
                    "dificuldade": "difícil",
                    "explosao": False,
                }],
            }]
        }
        self.client.force_login(self.mestre)
        with mock.patch(
            "controlador.chatbot._chamar_gemini",
            return_value=resposta_gemini,
        ):
            response = self.client.post(
                reverse("api_chatbot_campanha", args=[self.campanha.pk]),
                data=json.dumps({"comando": "Role algum teste"}),
                content_type="application/json",
            )

        dados = response.json()
        self.assertEqual(dados["mensagens"][0]["personagem"], "Aventureiro")
        rolagem = dados["mensagens"][0]["rolagens"][0]
        self.assertIn("erro", rolagem)
        self.assertEqual(rolagem["dados"], 20)

    def test_chatbot_report_is_saved_on_stop_and_displayed_in_history(self):
        ficha = FichaPersonagem.objects.create(
            usuario=self.jogador,
            nome="Aventureiro",
            aspecto="Corajoso",
        )
        FichaCampanha.objects.create(campanha=self.campanha, ficha=ficha)
        sessao = iniciar_sessao(self.campanha)
        sessao.chatbot_json = {
            "mensagens": [
                {"papel": "mestre", "texto": "Investigue o salão e anote que perdeu 5 PV"},
                {"papel": "assistente", "personagem": "Aventureiro", "texto": "Investigo. Perco 5 PV e fico com 15/20."},
            ]
        }
        sessao.save(update_fields=["chatbot_json"])

        relatorio = {
            "personagens": [{
                "personagem": "Aventureiro",
                "resumo": "Investigou o salão e encontrou pegadas.",
                "revisao": [
                    {"titulo": "Itens/Coletáveis", "acoes": ["Achou 3 moedas"]},
                    {"titulo": "Status/Integridade", "acoes": ["Perdeu 5 PV; PV atual = 15/20"]},
                ],
                "veredito": "Atento ao redor.",
            }]
        }
        self.client.force_login(self.mestre)
        with mock.patch(
            "controlador.chatbot._chamar_gemini",
            return_value=relatorio,
        ):
            response = self.client.post(
                reverse("parar_sessao_campanha", args=[self.campanha.pk])
            )

        self.assertEqual(response.status_code, 200)
        sessao.refresh_from_db()
        self.assertEqual(sessao.relatorio_json["personagens"][0]["personagem"], "Aventureiro")
        page = self.client.get(reverse("campanha", args=[self.campanha.pk]))
        self.assertContains(page, "VER RELATÓRIO DA IA")
        self.assertContains(page, "Relatório da sessão")

    def test_campaign_details_load_linked_sheets_in_one_query(self):
        nomes_fichas = []
        for numero in range(3):
            usuario = Usuario.objects.create_user(
                email=f"participante-{numero}@example.com",
                username=f"Participante{numero}",
                password="SenhaForte-2098!",
            )
            entrar_em_campanha(usuario, self.campanha.codigo_convite)
            ficha = FichaPersonagem.objects.create(
                usuario=usuario,
                nome=f"Ficha {numero}",
                aspecto="Aventureira",
            )
            FichaCampanha.objects.create(campanha=self.campanha, ficha=ficha)
            nomes_fichas.append(ficha.nome)

        self.client.force_login(self.mestre)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("campanha", args=[self.campanha.pk]))

        self.assertEqual(response.status_code, 200)
        for nome in nomes_fichas:
            self.assertContains(response, nome)
        ficha_queries = [
            query
            for query in queries.captured_queries
            if "controlador_fichacampanha" in query["sql"].lower()
        ]
        self.assertEqual(len(ficha_queries), 2)

    def test_shared_file_is_visible_only_to_campaign_members(self):
        entrar_em_campanha(self.jogador, self.campanha.codigo_convite)
        arquivo = Arquivo.objects.create(
            usuario=self.mestre,
            nome_original="handout.png",
            arquivo=ContentFile(valid_png(), name="handout.png"),
            tipo=Arquivo.Tipo.HANDOUT,
        )
        self.campanha.arquivos.add(arquivo)
        url = reverse("visualizar_arquivo", args=[arquivo.pk])

        self.client.force_login(self.jogador)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        response.close()

        self.client.force_login(self.espectador)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_shared_sheet_visibility_is_read_only_and_respects_campaign_rules(self):
        entrar_em_campanha(self.jogador, self.campanha.codigo_convite)
        entrar_em_campanha(self.espectador, self.campanha.codigo_convite)
        ficha = FichaPersonagem.objects.create(
            usuario=self.jogador,
            nome="Ficha compartilhada",
            aspecto="Exploradora",
        )
        FichaCampanha.objects.create(campanha=self.campanha, ficha=ficha)
        editor_url = f"{reverse('criador', args=[ficha.pk])}?campanha={self.campanha.pk}"
        api_url = f"{reverse('api_ficha', args=[ficha.pk])}?campanha={self.campanha.pk}"

        self.client.force_login(self.espectador)
        self.assertEqual(self.client.get(editor_url).status_code, 200)
        self.assertEqual(
            self.client.get(
                f"{reverse('api_ficha', args=[ficha.pk])}?campanha=not-an-id"
            ).status_code,
            404,
        )
        self.client.force_login(self.mestre)
        response = self.client.get(editor_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "const podeEditar = false;")
        self.assertNotContains(response, 'id="btn_modo_edicao"')
        self.assertEqual(self.client.get(api_url).status_code, 200)
        self.assertEqual(
            self.client.post(
                reverse("api_ficha", args=[ficha.pk]),
                data=json.dumps(
                    {
                        "nome": "Alterada",
                        "subtitulo": "Exploradora",
                        **ficha.estrutura_json,
                    }
                ),
                content_type="application/json",
            ).status_code,
            404,
        )

        ficha.estrutura_json["visibilidade"] = "mestres"
        ficha.save(update_fields=["estrutura_json"])
        self.client.force_login(self.espectador)
        self.assertEqual(self.client.get(editor_url).status_code, 404)
        self.client.force_login(self.jogador)
        self.assertEqual(self.client.get(editor_url).status_code, 200)
        self.client.force_login(self.mestre)
        self.assertEqual(self.client.get(editor_url).status_code, 200)