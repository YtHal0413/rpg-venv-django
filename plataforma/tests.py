import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .character_ai import InvalidCharacterSuggestion, generate_character_suggestion
from .models import Campaign, CharacterSheet, LibraryBook, PlayerProfile, SheetTemplate

User = get_user_model()


class CharacterAssistantTests(TestCase):
    @override_settings(GOOGLE_API_KEY="test-key", GEMINI_MODEL="gemini-test")
    @patch("plataforma.character_ai.async_to_sync")
    @patch("plataforma.character_ai.GoogleGenAIChatGenerator")
    def test_suggestion_uses_sdk_and_validates_json(self, generator_class, async_to_sync_mock):
        async_to_sync_mock.return_value.return_value = json.dumps(
            {
                "nome": "Liora",
                "aspecto": "Curandeira viajante",
                "conceito": "Procura recuperar os conhecimentos de sua ordem.",
            }
        )

        suggestion = generate_character_suggestion("Uma curandeira viajante")

        self.assertEqual(suggestion["nome"], "Liora")
        generator_class.assert_called_once()
        async_to_sync_mock.assert_called_once()

    @override_settings(GOOGLE_API_KEY="test-key")
    @patch("plataforma.character_ai.async_to_sync")
    @patch("plataforma.character_ai.GoogleGenAIChatGenerator")
    def test_suggestion_rejects_non_json_model_output(self, generator_class, async_to_sync_mock):
        async_to_sync_mock.return_value.return_value = "Isso não é JSON"

        with self.assertRaises(InvalidCharacterSuggestion):
            generate_character_suggestion("Uma curandeira viajante")


class PlataformaViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="mestre@example.com",
            email="mestre@example.com",
            password="senha-forte-123",
        )
        self.profile = PlayerProfile.objects.create(
            user=self.user, display_name="Mestre", activated=True
        )
        self.client.force_login(self.user)

    def create_sheet(self):
        response = self.client.post(
            reverse("criar_ficha"),
            {"nome_personagem": "Lina", "subtitulo": "Batedora"},
        )
        self.assertEqual(response.status_code, 302)
        return CharacterSheet.objects.get(owner=self.user, name="Lina")

    def test_login_page_and_authenticated_collection_render(self):
        self.client.logout()
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Entrar na Plataforma")

        self.client.force_login(self.user)
        response = self.client.get(reverse("colecoes"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Suas Coleções")

    @override_settings(GOOGLE_API_KEY="test-key")
    @patch("plataforma.views.generate_character_suggestion")
    def test_character_assistant_returns_suggestion_without_creating_sheet(self, generate_suggestion):
        generate_suggestion.return_value = {
            "nome": "Liora",
            "aspecto": "Curandeira de uma ordem esquecida",
            "conceito": "Viajante que procura recuperar os conhecimentos de sua ordem.",
        }

        response = self.client.post(
            reverse("api_assistente_personagem"),
            data=json.dumps({"ideia": "Uma curandeira viajante"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nome"], "Liora")
        self.assertFalse(CharacterSheet.objects.filter(owner=self.user).exists())
        generate_suggestion.assert_called_once_with("Uma curandeira viajante")

    def test_character_assistant_validates_prompt_and_api_key(self):
        for idea in (" ", ["entrada inválida"]):
            with self.subTest(idea=idea):
                response = self.client.post(
                    reverse("api_assistente_personagem"),
                    data=json.dumps({"ideia": idea}),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)

        with override_settings(GOOGLE_API_KEY=""):
            response = self.client.post(
                reverse("api_assistente_personagem"),
                data=json.dumps({"ideia": "Uma curandeira viajante"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 503)

    def test_character_assistant_respects_unlicensed_sheet_limit(self):
        self.profile.activated = False
        self.profile.save(update_fields=["activated"])
        CharacterSheet.objects.create(owner=self.user, name="Ficha existente")

        with patch("plataforma.views.generate_character_suggestion") as generate_suggestion:
            response = self.client.post(
                reverse("api_assistente_personagem"),
                data=json.dumps({"ideia": "Uma exploradora"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 403)
        generate_suggestion.assert_not_called()

    @override_settings(GOOGLE_API_KEY="test-key")
    def test_character_manager_shows_enabled_ai_assistant(self):
        response = self.client.get(reverse("selecao_personagens"))

        self.assertEqual(response.status_code, 200)
        rendered_page = response.content.decode()
        self.assertIn("Assistente de criação com IA", rendered_page)
        self.assertContains(response, "GERAR SUGESTÃO")
        self.assertLess(
            rendered_page.index("Assistente de criação com IA"),
            rendered_page.index('id="modal_nome_ficha"'),
        )

    @override_settings(GOOGLE_API_KEY="")
    def test_character_manager_explains_when_ai_key_is_missing(self):
        response = self.client.get(reverse("selecao_personagens"))

        self.assertContains(response, "IA INDISPONÍVEL")
        self.assertContains(response, "Configure GOOGLE_API_KEY no terminal")

    def test_registration_is_explicit_and_password_is_hashed(self):
        self.client.logout()
        response = self.client.post(
            reverse("login"),
            {"email": "novo@example.com", "senha": "SenhaForte_2026!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="novo@example.com").exists())

        response = self.client.post(
            reverse("cadastro"),
            {
                "nome": "Novo Jogador",
                "email": "novo@example.com",
                "senha": "SenhaForte_2026!",
                "confirmar_senha": "SenhaForte_2026!",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="novo@example.com")
        self.assertTrue(user.check_password("SenhaForte_2026!"))
        self.assertNotEqual(user.password, "SenhaForte_2026!")
        self.assertEqual(user.rpg_profile.display_name, "Novo Jogador")
        self.client.logout()
        response = self.client.post(
            reverse("cadastro"),
            {
                "nome": "Conta duplicada",
                "email": "NOVO@example.com",
                "senha": "SenhaForte_2026!",
                "confirmar_senha": "SenhaForte_2026!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email__iexact="novo@example.com").count(), 1)

    def test_unlicensed_quotas_and_unique_invite_code(self):
        self.profile.activated = False
        self.profile.save(update_fields=["activated"])

        response = self.client.post(
            reverse("criar_ficha"),
            {"nome_personagem": "Ficha gratuita", "subtitulo": "Única"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CharacterSheet.objects.filter(owner=self.user).exists())
        self.client.post(
            reverse("criar_ficha"),
            {"nome_personagem": "Segunda ficha", "subtitulo": "Bloqueada"},
        )
        self.assertFalse(CharacterSheet.objects.filter(name="Segunda ficha").exists())

        self.client.post(
            reverse("criar_campanha"),
            {"nome": "Campanha bloqueada", "descricao": ""},
        )
        self.assertFalse(Campaign.objects.filter(name="Campanha bloqueada").exists())

        first_master = User.objects.create_user(username="mestre1@example.com")
        second_master = User.objects.create_user(username="mestre2@example.com")
        first = Campaign.objects.create(master=first_master, name="Convite 1")
        second = Campaign.objects.create(master=second_master, name="Convite 2")
        first.players.add(self.user)
        response = self.client.post(
            reverse("entrar_campanha"),
            {"codigo_campanha": second.invite_code},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(second.players.filter(pk=self.user.pk).exists())
        self.assertNotEqual(first.invite_code, second.invite_code)

    def test_first_tab_is_protected_and_column_is_limited_to_three_tabs(self):
        sheet = self.create_sheet()
        data_url = reverse("api_obter_ficha", args=[sheet.pk])
        first_tab_id = self.client.get(data_url).json()["colunas"]["1"]["abas"][0]["id"]
        response = self.client.delete(
            f"{data_url}/aba/{first_tab_id}"
        )
        self.assertEqual(response.status_code, 404)

        for title in ("Tab 2", "Tab 3"):
            response = self.client.post(
                reverse("api_criar_aba", args=[sheet.pk]),
                data=json.dumps({"titulo": title, "posicaoColuna": 1}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("api_criar_aba", args=[sheet.pk]),
            data=json.dumps({"titulo": "Tab 4", "posicaoColuna": 1}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_sheet_save_rejects_malformed_and_oversized_payloads(self):
        sheet = self.create_sheet()
        url = reverse("api_obter_ficha", args=[sheet.pk])
        payload = self.client.get(url).json()
        payload["colunas"]["1"]["abas"][0]["secoes"] = [
            {"tipo": [], "componentes": []}
        ]
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            url,
            data=b" " * (1024 * 1024 + 1),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 413)

    def test_logout_requires_post_and_ends_session(self):
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("logout")).status_code, 302)
        response = self.client.get(reverse("colecoes"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('login')}?next=/colecoes")

    def test_existing_application_pages_render(self):
        sheet = self.create_sheet()
        campaign = Campaign.objects.create(master=self.user, name="Mesa")
        campaign.players.add(self.user)
        paths = [
            reverse("inicio"),
            reverse("perfil"),
            reverse("colecoes"),
            reverse("livros"),
            reverse("selecao_personagens"),
            reverse("gerenciar_campanhas"),
            reverse("criar_campanha"),
            reverse("campanha_detalhes", args=[campaign.pk]),
            reverse("criador_ficha", args=[sheet.pk]),
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_sheet_json_api_supports_structure_crud_and_templates(self):
        sheet = self.create_sheet()
        url = reverse("api_obter_ficha", args=[sheet.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["nome"], "Lina")
        self.assertIn("1", data["colunas"])

        response = self.client.post(
            reverse("api_criar_aba", args=[sheet.pk]),
            data=json.dumps({"titulo": "Combate", "posicaoColuna": 1}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        tab_id = response.json()["aba"]["id"]

        response = self.client.post(
            reverse("api_criar_secao", args=[sheet.pk]),
            data=json.dumps({"titulo": "Atributos", "abaId": tab_id, "tipo": "AtributoSimples"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        section_id = response.json()["secao"]["id"]

        response = self.client.post(
            reverse("api_criar_componente", args=[sheet.pk]),
            data=json.dumps({"secaoId": section_id, "tipo": "AtributoSimples", "nomeAtributo": "Força"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        component_id = response.json()["componente"]["id"]

        response = self.client.put(
            f"{url}/componente/{component_id}",
            data=json.dumps({"valorAtributo": 4}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["componente"]["valorAtributo"], 4)

        response = self.client.post(
            reverse("api_templates", args=[sheet.pk]),
            data=json.dumps({"nome": "Ficha base"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        template_id = response.json()["id"]
        self.assertTrue(SheetTemplate.objects.filter(pk=template_id, owner=self.user).exists())

        response = self.client.delete(f"{url}/componente/{component_id}")
        self.assertEqual(response.status_code, 200)
        response = self.client.delete(f"{url}/aba/{tab_id}")
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("api_aplicar_template", args=[sheet.pk, template_id]),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nome"], "Lina")

    def test_campaign_access_and_character_sharing(self):
        sheet = self.create_sheet()
        campaign = Campaign.objects.create(master=self.user, name="Aventura")
        campaign.players.add(self.user)
        campaign.characters.add(sheet)

        response = self.client.get(reverse("campanha_detalhes", args=[campaign.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aventura")

        other_user = User.objects.create_user(
            username="jogador@example.com",
            email="jogador@example.com",
            password="senha-forte-456",
        )
        PlayerProfile.objects.create(user=other_user, display_name="Jogador")
        campaign.players.add(other_user)
        self.client.force_login(other_user)
        response = self.client.get(reverse("api_obter_ficha", args=[sheet.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nome"], "Lina")

    def test_activation_key_unlocks_creation(self):
        self.profile.activated = False
        self.profile.save(update_fields=["activated"])
        response = self.client.post(
            reverse("criar_ficha"),
            {"nome_personagem": "Bloqueado"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CharacterSheet.objects.filter(name="Bloqueado").exists())

        response = self.client.post(
            reverse("criar_campanha"),
            {"nome": "Campanha bloqueada", "descricao": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Campaign.objects.filter(name="Campanha bloqueada").exists())

    def test_pdf_library_upload_and_removal(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                upload = SimpleUploadedFile(
                    "manual.pdf", b"%PDF-1.4\nsample document", content_type="application/pdf"
                )
                response = self.client.post(reverse("livros"), {"livro_pdf": upload})
                self.assertEqual(response.status_code, 302)
                response = self.client.get(reverse("livros"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "manual.pdf")

                response = self.client.post(
                    reverse("livros"),
                    {"deletar_livro": self.user.rpg_library_books.get().pk},
                )
                self.assertEqual(response.status_code, 302)
                self.assertFalse(self.user.rpg_library_books.exists())

    def test_library_validates_content_and_protects_files_from_other_users(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                invalid = SimpleUploadedFile(
                    "not-a-pdf.pdf", b"not a real PDF", content_type="application/pdf"
                )
                self.client.post(reverse("livros"), {"livro_pdf": invalid})
                self.assertFalse(self.user.rpg_library_books.exists())

                valid_pdf = SimpleUploadedFile(
                    "handout.pdf", b"%PDF-1.7\nsample", content_type="application/pdf"
                )
                self.client.post(reverse("livros"), {"livro_pdf": valid_pdf})
                book = self.user.rpg_library_books.get()
                file_url = reverse("livro_arquivo", args=[book.pk])
                other_user = User.objects.create_user(
                    username="outro@example.com",
                    email="outro@example.com",
                    password="OutraSenhaForte_2026!",
                )
                self.client.force_login(other_user)
                self.assertEqual(self.client.get(file_url).status_code, 404)
                self.client.force_login(self.user)
                response = self.client.get(file_url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/pdf")
                response.close()

    def test_campaign_file_access_and_master_can_remove_participant(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                upload = SimpleUploadedFile(
                    "handout.png",
                    b"\x89PNG\r\n\x1a\nimage",
                    content_type="image/png",
                )
                self.client.post(reverse("livros"), {"livro_pdf": upload})
                book = self.user.rpg_library_books.get()
                campaign = Campaign.objects.create(master=self.user, name="Mesa compartilhada")
                campaign.players.add(self.user)
                campaign.library_books.add(book)

                participant = User.objects.create_user(username="participante@example.com")
                PlayerProfile.objects.create(user=participant, display_name="Participante")
                campaign.players.add(participant)
                self.client.force_login(participant)
                response = self.client.get(reverse("livro_arquivo", args=[book.pk]))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "image/png")
                response.close()

                self.client.force_login(self.user)
                response = self.client.post(
                    reverse(
                        "remover_participante",
                        args=[campaign.pk, participant.pk],
                    )
                )
                self.assertEqual(response.status_code, 302)
                self.assertFalse(campaign.players.filter(pk=participant.pk).exists())
                self.assertTrue(LibraryBook.objects.filter(pk=book.pk).exists())

                self.client.force_login(participant)
                self.assertEqual(
                    self.client.get(reverse("livro_arquivo", args=[book.pk])).status_code,
                    404,
                )

    def test_character_avatar_can_be_uploaded_and_removed(self):
        sheet = self.create_sheet()
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                invalid_upload = SimpleUploadedFile(
                    "portrait.png", b"not a PNG image", content_type="image/png"
                )
                response = self.client.post(
                    reverse("api_upload_avatar_personagem", args=[sheet.pk]),
                    {"avatar": invalid_upload},
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("PNG, JPG ou JPEG", response.json()["erro"])

                upload = SimpleUploadedFile(
                    "portrait.png", b"\x89PNG\r\n\x1a\nsample image data", content_type="image/png"
                )
                response = self.client.post(
                    reverse("api_upload_avatar_personagem", args=[sheet.pk]),
                    {"avatar": upload},
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["avatar_url"].startswith("/media/"))

                payload = self.client.get(reverse("api_obter_ficha", args=[sheet.pk])).json()
                payload["avatar"] = None
                response = self.client.post(
                    reverse("api_obter_ficha", args=[sheet.pk]),
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 200)
                sheet.refresh_from_db()
                self.assertEqual(sheet.avatar_path, "")


class DjangoCsrfTests(TestCase):
    def test_login_form_has_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)
        response = client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", client.cookies)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        credentials = {"email": "csrf@example.com", "senha": "SenhaForte_2026!"}
        self.assertEqual(client.post(reverse("login"), credentials).status_code, 403)
        csrf_token = client.cookies["csrftoken"].value
        response = client.post(
            reverse("cadastro"),
            {
                **credentials,
                "nome": "Conta CSRF",
                "confirmar_senha": credentials["senha"],
            },
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 302)

    def test_logout_requires_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)
        user = User.objects.create_user(username="logout@example.com")
        client.force_login(user)
        self.assertEqual(client.get(reverse("perfil")).status_code, 200)

        self.assertEqual(client.post(reverse("logout")).status_code, 403)
        csrf_token = client.cookies["csrftoken"].value
        self.assertEqual(
            client.post(
                reverse("logout"),
                HTTP_X_CSRFTOKEN=csrf_token,
            ).status_code,
            302,
        )
