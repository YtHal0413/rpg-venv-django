import secrets
import string

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Chave, Usuario


_KEY_ALPHABET = string.ascii_uppercase + string.digits
_KEY_GENERATION_ATTEMPTS = 5


class ChaveIndisponivel(Exception):
    pass


def _novo_codigo():
    grupos = (4, 4, 4, 3)
    return "-".join(
        "".join(secrets.choice(_KEY_ALPHABET) for _ in range(tamanho))
        for tamanho in grupos
    )


def comprar_chave(usuario):
    for _ in range(_KEY_GENERATION_ATTEMPTS):
        codigo = _novo_codigo()
        try:
            with transaction.atomic():
                chave = Chave.objects.create(codigo=codigo, usuario=usuario)
        except IntegrityError:
            if not Chave.objects.filter(pk=codigo).exists():
                raise
            continue
        return chave

    raise RuntimeError("Não foi possível gerar uma chave única após várias tentativas.")


@transaction.atomic
def resgatar_chave(usuario, codigo):
    atualizadas = Chave.objects.filter(
        codigo=codigo,
        usuario=usuario,
        foi_usada=False,
    ).update(
        foi_usada=True,
        resgatada_em=timezone.now(),
    )
    if atualizadas != 1:
        raise ChaveIndisponivel(
            "Chave inválida, já resgatada ou vinculada a outra conta."
        )

    usuario_atualizado = Usuario.objects.get(pk=usuario.pk)
    if not usuario_atualizado.tem_chave:
        usuario_atualizado.tem_chave = True
        usuario_atualizado.save(update_fields=["tem_chave"])

    return Chave.objects.get(codigo=codigo)


def tem_acesso_ilimitado(usuario):
    return bool(usuario.is_authenticated and usuario.tem_chave)


def pode_criar_ficha(usuario, fichas_ativas):
    return tem_acesso_ilimitado(usuario) or fichas_ativas < 1


def pode_participar_campanha(usuario, campanhas_ativas):
    return tem_acesso_ilimitado(usuario) or campanhas_ativas < 1


def pode_criar_campanha(usuario):
    return tem_acesso_ilimitado(usuario)
