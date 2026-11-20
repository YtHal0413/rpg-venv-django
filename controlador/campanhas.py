import secrets
import string
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    Campanha,
    CampanhaParticipante,
    FichaCampanha,
    SessaoCampanha,
    Usuario,
)
from .services import pode_criar_campanha, pode_participar_campanha


_ALFABETO_CODIGO = string.ascii_uppercase + string.digits
_TENTATIVAS_CODIGO = 5


class LimiteCampanhaAtingido(Exception):
    pass


def _novo_codigo_convite():
    grupos = (3, 3, 2)
    return "-".join(
        "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(tamanho))
        for tamanho in grupos
    )


def criar_campanha(mestre, titulo, descricao=""):
    titulo = titulo.strip() if isinstance(titulo, str) else ""
    descricao = descricao.strip() if isinstance(descricao, str) else ""
    if not titulo or len(titulo) > 100:
        raise ValidationError("Informe um título com até 100 caracteres.")
    if len(descricao) > 10000:
        raise ValidationError("A descrição deve ter no máximo 10.000 caracteres.")
    if not pode_criar_campanha(mestre):
        raise LimiteCampanhaAtingido(
            "Somente contas com acesso ilimitado podem criar campanhas."
        )

    for _ in range(_TENTATIVAS_CODIGO):
        codigo = _novo_codigo_convite()
        try:
            with transaction.atomic():
                campanha = Campanha.objects.create(
                    mestre=mestre,
                    titulo=titulo,
                    descricao=descricao,
                    codigo_convite=codigo,
                )
                CampanhaParticipante.objects.create(
                    campanha=campanha,
                    usuario=mestre,
                    ultimo_acesso=timezone.now(),
                )
            return campanha
        except IntegrityError:
            if not Campanha.objects.filter(codigo_convite=codigo).exists():
                raise

    raise RuntimeError(
        "Não foi possível gerar um código de convite único após várias tentativas."
    )


@transaction.atomic
def entrar_em_campanha(usuario, codigo):
    """Aplica o limite de participação dentro da mesma transação do ingresso."""
    codigo = codigo.strip().upper() if isinstance(codigo, str) else ""
    campanha = Campanha.objects.select_for_update().filter(
        codigo_convite=codigo
    ).first()
    if campanha is None:
        raise Campanha.DoesNotExist

    vinculo = CampanhaParticipante.objects.filter(
        campanha=campanha,
        usuario=usuario,
    ).first()
    if vinculo:
        vinculo.ultimo_acesso = timezone.now()
        vinculo.save(update_fields=["ultimo_acesso"])
        return campanha, False

    Usuario.objects.select_for_update().get(pk=usuario.pk)
    campanhas_ativas = CampanhaParticipante.objects.filter(
        usuario=usuario
    ).count()
    if not pode_participar_campanha(usuario, campanhas_ativas):
        raise LimiteCampanhaAtingido(
            "Sua conta básica pode participar de apenas uma campanha por vez."
        )
    CampanhaParticipante.objects.create(
        campanha=campanha,
        usuario=usuario,
        ultimo_acesso=timezone.now(),
    )
    return campanha, True


@transaction.atomic
def sair_da_campanha(campanha, usuario):
    if campanha.mestre_id == usuario.pk:
        raise ValidationError("O mestre não pode sair da própria campanha.")
    vinculo = CampanhaParticipante.objects.filter(
        campanha=campanha,
        usuario=usuario,
    ).first()
    if vinculo is None:
        raise ValidationError("Você não participa desta campanha.")
    FichaCampanha.objects.filter(
        campanha=campanha,
        ficha__usuario=usuario,
    ).delete()
    vinculo.delete()


@transaction.atomic
def remover_participante(campanha, usuario):
    if campanha.mestre_id == usuario.pk:
        raise ValidationError("O mestre não pode ser removido da campanha.")
    FichaCampanha.objects.filter(
        campanha=campanha,
        ficha__usuario=usuario,
    ).delete()
    removidos, _ = CampanhaParticipante.objects.filter(
        campanha=campanha,
        usuario=usuario,
    ).delete()
    if not removidos:
        raise ValidationError("O usuário não participa desta campanha.")


def iniciar_sessao(campanha):
    """Registra na sessão os participantes online que não são espectadores."""
    agora = timezone.now()
    limite_online = agora - timedelta(seconds=90)
    with transaction.atomic():
        campanha = Campanha.objects.select_for_update().get(pk=campanha.pk)
        if SessaoCampanha.objects.filter(
            campanha=campanha,
            encerrada_em__isnull=True,
        ).exists():
            raise ValidationError("Já existe uma sessão em andamento.")

        membros_online = CampanhaParticipante.objects.filter(
            campanha=campanha,
            ultimo_acesso__gte=limite_online,
        ).select_related("usuario")
        fichas_por_usuario = {}
        for usuario_id, nome_ficha in FichaCampanha.objects.filter(
            campanha=campanha
        ).values_list("ficha__usuario_id", "ficha__nome"):
            fichas_por_usuario.setdefault(usuario_id, []).append(nome_ficha)

        presentes = []
        for vinculo in membros_online:
            fichas = fichas_por_usuario.get(vinculo.usuario_id, [])
            eh_mestre = vinculo.usuario_id == campanha.mestre_id
            if not eh_mestre and not fichas:
                continue
            presentes.append(
                {
                    "usuario_id": vinculo.usuario_id,
                    "nome": vinculo.usuario.username,
                    "mestre": eh_mestre,
                    "fichas": fichas,
                }
            )

        return SessaoCampanha.objects.create(
            campanha=campanha,
            iniciada_em=agora,
            participantes_json=presentes,
        )


@transaction.atomic
def parar_sessao(campanha):
    sessao = SessaoCampanha.objects.select_for_update().filter(
        campanha=campanha,
        encerrada_em__isnull=True,
    ).first()
    if sessao is None:
        raise ValidationError("Não há sessão em andamento.")
    sessao.encerrada_em = timezone.now()
    sessao.duracao_segundos = max(
        0,
        int((sessao.encerrada_em - sessao.iniciada_em).total_seconds()),
    )
    sessao.save(update_fields=["encerrada_em", "duracao_segundos"])
    return sessao
