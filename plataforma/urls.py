from django.urls import path

from . import views


urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("login", views.login_view, name="login"),
    path("cadastro", views.cadastro, name="cadastro"),
    path("logout", views.logout_view, name="logout"),
    path("perfil", views.perfil, name="perfil"),
    path("resgate", views.resgate, name="resgate"),
    path("colecoes", views.colecoes, name="colecoes"),
    path("campanha/criar", views.criar_campanha, name="criar_campanha"),
    path("campanha/entrar", views.entrar_campanha, name="entrar_campanha"),
    path("campanha/<int:id_campanha>", views.campanha_detalhes, name="campanha_detalhes"),
    path(
        "campanha/<int:id_campanha>/anexar_arquivo",
        views.anexar_arquivo_campanha,
        name="anexar_arquivo_campanha",
    ),
    path(
        "campanha/<int:id_campanha>/remover_arquivo",
        views.remover_arquivo_campanha,
        name="remover_arquivo_campanha",
    ),
    path(
        "campanha/<int:id_campanha>/vincular_ficha",
        views.vincular_ficha_campanha,
        name="vincular_ficha_campanha",
    ),
    path(
        "campanha/<int:id_campanha>/remover_ficha",
        views.remover_ficha_campanha,
        name="remover_ficha_campanha",
    ),
    path("livros", views.livros, name="livros"),
    path("personagens", views.selecao_personagens, name="selecao_personagens"),
    path(
        "api/personagens/assistente",
        views.api_assistente_personagem,
        name="api_assistente_personagem",
    ),
    path("ficha/selecao", views.selecao_criacao, name="selecao_criacao"),
    path("personagens/<int:id_ficha>/excluir", views.excluir_personagem, name="excluir_personagem"),
    path("ficha/criar", views.criar_ficha, name="criar_ficha"),
    path("criador/<int:id_ficha>", views.criador_ficha, name="criador_ficha"),
    path("campanhas", views.gerenciar_campanhas, name="gerenciar_campanhas"),
    path("campanha/<int:id_campanha>/excluir", views.excluir_campanha, name="excluir_campanha"),
    path("campanha/<int:id_campanha>/sair", views.sair_campanha, name="sair_campanha"),
    path(
        "campanha/<int:id_campanha>/participante/<int:participante_id>/remover",
        views.remover_participante,
        name="remover_participante",
    ),
    path("biblioteca/arquivo/<int:livro_id>", views.livro_arquivo, name="livro_arquivo"),
    path("media/<path:caminho>", views.arquivo_midia, name="arquivo_midia"),
    path("api/ficha/<int:id_ficha>", views.api_ficha, name="api_obter_ficha"),
    path("api/ficha/<int:id_ficha>/salvar", views.api_salvar_ficha, name="api_salvar_ficha"),
    path(
        "api/ficha/<int:id_ficha>/avatar",
        views.api_upload_avatar_personagem,
        name="api_upload_avatar_personagem",
    ),
    path("api/ficha/<int:id_ficha>/template", views.api_templates, name="api_templates"),
    path(
        "api/ficha/<int:id_ficha>/template/<int:template_id>/apply",
        views.api_aplicar_template,
        name="api_aplicar_template",
    ),
    path(
        "api/ficha/<int:id_ficha>/template/<int:template_id>",
        views.api_template_item,
        name="api_template_item",
    ),
    path("api/ficha/<int:id_ficha>/aba", views.api_criar_aba, name="api_criar_aba"),
    path(
        "api/ficha/<int:id_ficha>/aba/<int:aba_id>",
        views.api_deletar_aba,
        name="api_deletar_aba",
    ),
    path("api/ficha/<int:id_ficha>/secao", views.api_criar_secao, name="api_criar_secao"),
    path(
        "api/ficha/<int:id_ficha>/secao/<int:secao_id>",
        views.api_deletar_secao,
        name="api_deletar_secao",
    ),
    path(
        "api/ficha/<int:id_ficha>/componente",
        views.api_criar_componente,
        name="api_criar_componente",
    ),
    path(
        "api/ficha/<int:id_ficha>/componente/<int:comp_id>",
        views.api_componente_item,
        name="api_componente_item",
    ),
]
