from django.contrib import admin
from django.urls import path

from controlador import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", views.inicio, name="inicio"),
    path("login/", views.login_view, name="login"),
    path("cadastro/", views.cadastro_view, name="cadastro"),
    path("perfil/", views.perfil, name="perfil"),
    path("conta/avatar/", views.avatar_proprio, name="avatar_proprio"),
    path("chaves/comprar/", views.comprar_chave_view, name="comprar_chave"),
    path("chaves/resgatar/", views.resgatar_chave_view, name="resgatar_chave"),
    path("logout/", views.logout_view, name="logout"),
    path("arquivos/", views.biblioteca, name="livros"),
    path("livros/", views.biblioteca, name="biblioteca"),
    path("personagens/", views.personagens, name="personagens"),
    path("ficha/criar/", views.criar_ficha_view, name="criar_ficha"),
    path(
        "personagens/<int:ficha_id>/excluir/",
        views.excluir_ficha_view,
        name="excluir_personagem",
    ),
    path("ficha/selecao/", views.personagens, name="selecao_ficha"),
    path("criador/<int:ficha_id>/", views.criador_ficha, name="criador"),
    path("api/ficha/<int:ficha_id>", views.api_ficha, name="api_ficha"),
    path(
        "api/ficha/<int:ficha_id>/avatar",
        views.api_avatar_ficha,
        name="api_avatar_ficha",
    ),
    path(
        "fichas/<int:ficha_id>/avatar/",
        views.avatar_ficha,
        name="avatar_ficha",
    ),
    path(
        "api/ficha/<int:ficha_id>/template",
        views.api_templates_ficha,
        name="api_templates_ficha",
    ),
    path(
        "api/ficha/<int:ficha_id>/template/<int:template_id>/apply",
        views.api_aplicar_template_ficha,
        name="api_aplicar_template_ficha",
    ),
    path(
        "api/ficha/<int:ficha_id>/template/<int:template_id>",
        views.api_excluir_template_ficha,
        name="api_excluir_template_ficha",
    ),
    path(
        "api/ficha/<int:ficha_id>/aba",
        views.api_criar_aba_ficha,
        name="api_criar_aba_ficha",
    ),
    path(
        "api/ficha/<int:ficha_id>/aba/<int:aba_id>",
        views.api_excluir_aba_ficha,
        name="api_excluir_aba_ficha",
    ),
    path(
        "api/ficha/<int:ficha_id>/secao",
        views.api_criar_secao_ficha,
        name="api_criar_secao_ficha",
    ),
    path(
        "api/ficha/<int:ficha_id>/secao/<int:secao_id>",
        views.api_excluir_secao_ficha,
        name="api_excluir_secao_ficha",
    ),
    path(
        "api/ficha/<int:ficha_id>/componente",
        views.api_criar_componente_ficha,
        name="api_criar_componente_ficha",
    ),
    path(
        "api/ficha/<int:ficha_id>/componente/<int:componente_id>",
        views.api_atualizar_componente_ficha,
        name="api_atualizar_componente_ficha",
    ),
    path(
        "arquivos/<int:arquivo_id>/visualizar/",
        views.visualizar_arquivo,
        name="visualizar_arquivo",
    ),
    path(
        "arquivos/<int:arquivo_id>/remover/",
        views.remover_arquivo,
        name="remover_arquivo",
    ),
    path("colecoes/", views.colecoes, name="colecoes"),
    path("campanhas/", views.gerenciar_campanhas, name="campanhas"),
    path("campanha/criar/", views.criar_campanha_view, name="criar_campanha"),
    path("campanha/entrar/", views.entrar_campanha_view, name="entrar_campanha"),
    path(
        "campanha/<int:campanha_id>/",
        views.campanha_detalhes,
        name="campanha",
    ),
    path(
        "campanha/<int:campanha_id>/excluir/",
        views.excluir_campanha_view,
        name="excluir_campanha",
    ),
    path(
        "campanha/<int:campanha_id>/sair/",
        views.sair_campanha_view,
        name="sair_campanha",
    ),
    path(
        "campanha/<int:campanha_id>/participante/<int:usuario_id>/remover/",
        views.remover_participante_view,
        name="remover_participante_campanha",
    ),
    path(
        "campanha/<int:campanha_id>/ficha/vincular/",
        views.vincular_ficha_campanha_view,
        name="vincular_ficha_campanha",
    ),
    path(
        "campanha/<int:campanha_id>/ficha/<int:ficha_id>/remover/",
        views.remover_ficha_campanha_view,
        name="remover_ficha_campanha",
    ),
    path(
        "campanha/<int:campanha_id>/arquivo/vincular/",
        views.vincular_arquivo_campanha_view,
        name="vincular_arquivo_campanha",
    ),
    path(
        "campanha/<int:campanha_id>/arquivo/<int:arquivo_id>/remover/",
        views.remover_arquivo_campanha_view,
        name="remover_arquivo_campanha",
    ),
    path(
        "campanha/<int:campanha_id>/template/vincular/",
        views.vincular_template_campanha_view,
        name="vincular_template_campanha",
    ),
    path(
        "campanha/<int:campanha_id>/template/remover/",
        views.remover_template_campanha_view,
        name="remover_template_campanha",
    ),
    path(
        "campanha/<int:campanha_id>/template/copiar/",
        views.copiar_template_campanha_view,
        name="copiar_template_campanha",
    ),
    path(
        "api/campanha/<int:campanha_id>/presenca/",
        views.api_presenca_campanha,
        name="api_presenca_campanha",
    ),
    path(
        "api/campanha/<int:campanha_id>/sessao/iniciar/",
        views.iniciar_sessao_campanha_view,
        name="iniciar_sessao_campanha",
    ),
    path(
        "api/campanha/<int:campanha_id>/sessao/parar/",
        views.parar_sessao_campanha_view,
        name="parar_sessao_campanha",
    ),
    path(
        "api/campanha/<int:campanha_id>/chatbot/",
        views.api_chatbot_campanha,
        name="api_chatbot_campanha",
    ),
]

urlpatterns += [
    path("<path:caminho>", views.pagina_provisoria, name="pagina_provisoria"),
]
