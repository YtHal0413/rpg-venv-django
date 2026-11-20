import json
import random
import urllib.request
import urllib.error
from urllib.parse import urlencode

from django.conf import settings
from django.utils import timezone

from .models import FichaCampanha


class GeminiIndisponivel(Exception):
    pass


def personagens_faltosos(sessao):
    presentes = {
        item.get("usuario_id")
        for item in (sessao.participantes_json or [])
        if item.get("usuario_id") is not None
    }
    return list(
        FichaCampanha.objects.filter(campanha=sessao.campanha)
        .exclude(ficha__usuario_id__in=presentes)
        .select_related("ficha", "ficha__usuario")
        .values(
            "ficha_id",
            "ficha__nome",
            "ficha__aspecto",
            "ficha__estrutura_json",
            "ficha__usuario_id",
            "ficha__usuario__username",
        )
    )


def _chamar_gemini(prompt):
    chave = getattr(settings, "GEMINI_API_KEY", "")
    if not chave:
        return None

    modelo_configurado = getattr(
        settings,
        "GEMINI_MODEL",
        "gemini-3.1-flash-lite",
    )
    modelos = list(dict.fromkeys([
        modelo_configurado,
        "gemini-3.1-flash-lite",
        "gemini-flash-latest",
    ]))
    corpo = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "responseMimeType": "application/json",
            },
        }
    ).encode("utf-8")
    ultimo_erro = None
    for modelo in modelos:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{modelo}:generateContent?{urlencode({'key': chave})}"
        )
        requisicao = urllib.request.Request(
            url,
            data=corpo,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(requisicao, timeout=30) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
            texto = dados["candidates"][0]["content"]["parts"][0]["text"]
            try:
                return json.loads(texto)
            except json.JSONDecodeError:
                return {"mensagens": [{"personagem": "Narrador", "texto": texto}]}
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError) as erro:
            ultimo_erro = erro
    raise GeminiIndisponivel(
        "Não foi possível consultar o Gemini. Verifique a chave, o modelo e o acesso à API."
    ) from ultimo_erro


def _rolar(quantidade, dados, dificuldade=None, explosao=False):
    quantidade = max(1, min(int(quantidade or 1), 100))
    dados = max(2, min(int(dados or 20), 100))
    resultados = []
    sucessos = 0
    for _ in range(quantidade):
        resultado = random.randint(1, dados)
        resultados.append(resultado)
        if dificuldade is not None:
            sucessos += int(resultado >= int(dificuldade))
        if explosao and resultado == dados:
            forca_extra = random.randint(1, dados)
            resultados.append(forca_extra)
            if dificuldade is not None:
                sucessos += int(forca_extra >= int(dificuldade))
    return {
        "dados": dados,
        "quantidade": quantidade,
        "resultados": resultados,
        "dificuldade": dificuldade,
        "sucessos": sucessos if dificuldade is not None else None,
        "explosao": explosao,
    }


def enviar_comando(sessao, comando):
    faltosos = personagens_faltosos(sessao)
    if not faltosos:
        return {
            "mensagens": [{
                "personagem": "Sistema",
                "texto": "Não há personagens faltosos nesta sessão.",
            }],
            "faltosos": [],
        }

    estado = sessao.chatbot_json if isinstance(sessao.chatbot_json, dict) else {}
    mensagens = estado.setdefault("mensagens", [])
    historico = list(
        sessao.campanha.sessoes.exclude(pk=sessao.pk)
        .filter(relatorio_json__isnull=False)
        .order_by("-iniciada_em")[:3]
        .values_list("relatorio_json", flat=True)
    )
    contexto = [
        {
            "ficha_id": item["ficha_id"],
            "nome": item["ficha__nome"],
            "aspecto": item["ficha__aspecto"],
            "jogador": item["ficha__usuario__username"],
            "estrutura": item["ficha__estrutura_json"],
        }
        for item in faltosos
    ]
    prompt = (
        "Você interpreta personagens de jogadores ausentes em uma sessão de RPG. "
        "Responda apenas em português brasileiro, de forma coerente com cada ficha, "
        "contexto da cena e personalidade. Não invente mudanças permanentes sem dados. "
        "Se o mestre pedir uma rolagem, decida quantidade, dados, dificuldade e explosão. "
        "Retorne JSON no formato: "
        '{"mensagens":[{"personagem":"nome","texto":"ação ou fala","rolagens":[{"teste":"nome","quantidade":1,"dados":20,"dificuldade":10,"explosao":false}]}]}. '
        f"Fichas dos faltosos: {json.dumps(contexto, ensure_ascii=False)}. "
        f"Histórico anterior: {json.dumps(historico, ensure_ascii=False)}. "
        f"Contexto desta conversa: {json.dumps(mensagens[-20:], ensure_ascii=False)}. "
        f"Comando do mestre: {comando}"
    )

    try:
        resultado = _chamar_gemini(prompt)
    except GeminiIndisponivel as erro:
        resultado = {
            "mensagens": [{
                "personagem": context_name(faltosos),
                "texto": str(erro),
            }],
        }
    if resultado is None:
        resultado = {
            "mensagens": [{
                "personagem": context_name(faltosos),
                "texto": (
                    "Posso interpretar os personagens faltosos, mas a integração Gemini "
                    "não está configurada neste ambiente. Configure GEMINI_API_KEY."
                ),
            }],
        }
    elif not isinstance(resultado, dict):
        resultado = {"mensagens": [{"personagem": "Narrador", "texto": str(resultado)}]}

    mensagens_usuario = {
        "papel": "mestre",
        "texto": comando,
        "criado_em": timezone.now().isoformat(),
    }
    mensagens.append(mensagens_usuario)
    saidas = resultado.get("mensagens") or []
    for saida in saidas:
        saida["rolagens"] = [
            _executar_rolagem(rolagem)
            for rolagem in (saida.get("rolagens") or [])
        ]
        saida["papel"] = "assistente"
        saida["criado_em"] = timezone.now().isoformat()
        mensagens.append(saida)
    estado["mensagens"] = mensagens[-200:]
    sessao.chatbot_json = estado
    sessao.save(update_fields=["chatbot_json"])
    return {"mensagens": saidas, "faltosos": [item["ficha__nome"] for item in faltosos]}


def _executar_rolagem(rolagem):
    if not isinstance(rolagem, dict):
        return {}
    return _rolar(
        rolagem.get("quantidade", 1),
        rolagem.get("dados", 20),
        rolagem.get("dificuldade"),
        bool(rolagem.get("explosao")),
    ) | {"teste": rolagem.get("teste", "Teste")}


def context_name(faltosos):
    if len(faltosos) == 1:
        return faltosos[0]["ficha__nome"]
    return "Personagens faltosos"


def gerar_relatorio(sessao):
    faltosos = personagens_faltosos(sessao)
    estado = sessao.chatbot_json if isinstance(sessao.chatbot_json, dict) else {}
    mensagens = estado.get("mensagens", [])
    if not faltosos or not mensagens:
        return None

    fichas = [
        {
            "nome": item["ficha__nome"],
            "aspecto": item["ficha__aspecto"],
            "estrutura": item["ficha__estrutura_json"],
        }
        for item in faltosos
    ]
    prompt = (
        "Resuma a sessão de cada personagem ausente no formato JSON desta forma: "
        '{"personagens":[{"personagem":"nome","resumo":"texto corrido",'
        '"revisao":[{"titulo":"Itens/Coletáveis","acoes":["ação + componente + contexto"]}],'
        '"veredito":"sensação ou estado ao fim da sessão"}]}. '
        "Use português brasileiro e mudanças observadas nesta conversa. "
        f"Fichas: {json.dumps(fichas, ensure_ascii=False)}. "
        f"Conversa: {json.dumps(mensagens[-200:], ensure_ascii=False)}."
    )
    try:
        resultado = _chamar_gemini(prompt)
    except GeminiIndisponivel:
        resultado = None
    if not isinstance(resultado, dict) or not resultado.get("personagens"):
        personagens = []
        for ficha in fichas:
            personagens.append({
                "personagem": ficha["nome"],
                "resumo": "A IA interpretou o personagem durante esta sessão.",
                "revisao": [{"titulo": "Revisão da ficha", "acoes": []}],
                "veredito": "Estado final não informado pela integração.",
            })
        resultado = {"personagens": personagens}
    sessao.relatorio_json = resultado
    sessao.save(update_fields=["relatorio_json"])
    return resultado
