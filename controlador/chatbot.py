import json
import logging
import random
import re
import time
import urllib.request
import urllib.error

from django.conf import settings
from django.utils import timezone

from .models import FichaCampanha


logger = logging.getLogger(__name__)


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
        "gemini-3.5-flash-lite",
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
    ultimo_codigo_http = None
    ultimo_status_api = ""
    for indice_modelo, modelo in enumerate(modelos):
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{modelo}:generateContent"
        )
        requisicao = urllib.request.Request(
            url,
            data=corpo,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": chave,
            },
            method="POST",
        )
        tentativas = 2 if indice_modelo == 0 else 1
        for tentativa in range(tentativas):
            try:
                with urllib.request.urlopen(requisicao, timeout=30) as resposta:
                    dados = json.loads(resposta.read().decode("utf-8"))
                texto = dados["candidates"][0]["content"]["parts"][0]["text"]
                try:
                    resultado = json.loads(texto)
                    if isinstance(resultado, list):
                        return {"mensagens": resultado}
                    if (
                        isinstance(resultado, dict)
                        and "mensagens" not in resultado
                        and "personagem" in resultado
                    ):
                        return {
                            "mensagens": [{
                                "personagem": resultado.get("personagem"),
                                "texto": resultado.get("texto") or resultado.get("mensagem", ""),
                            }],
                        }
                    return resultado
                except json.JSONDecodeError:
                    return {"mensagens": [{"personagem": "Narrador", "texto": texto}]}
            except urllib.error.HTTPError as erro:
                ultimo_erro = erro
                ultimo_codigo_http = erro.code
                ultimo_status_api, mensagem_api = _detalhes_erro_gemini(erro, chave)
                logger.warning(
                    "Gemini retornou HTTP %s para o modelo %s (status=%s): %s",
                    erro.code,
                    modelo,
                    ultimo_status_api or "desconhecido",
                    mensagem_api or "a API não forneceu detalhes",
                )
                if erro.code == 404:
                    break
                if erro.code == 503:
                    if tentativa + 1 < tentativas:
                        time.sleep(random.uniform(1.0, 2.0))
                        continue
                    break
                raise GeminiIndisponivel(
                    _mensagem_erro_gemini(erro.code, ultimo_status_api)
                ) from erro
            except (
                urllib.error.URLError,
                TimeoutError,
                json.JSONDecodeError,
                KeyError,
                IndexError,
            ) as erro:
                logger.warning(
                    "Falha na chamada Gemini para o modelo %s (%s)",
                    modelo,
                    type(erro).__name__,
                )
                raise GeminiIndisponivel(
                    "Não foi possível concluir a chamada ao Gemini. "
                    "Verifique a conexão e consulte o log do servidor."
                ) from erro
    raise GeminiIndisponivel(
        _mensagem_erro_gemini(ultimo_codigo_http, ultimo_status_api)
    ) from ultimo_erro


def _detalhes_erro_gemini(erro, chave):
    try:
        dados = json.loads(erro.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "", ""
    if not isinstance(dados, dict):
        return "", ""
    detalhes = dados.get("error", {})
    if not isinstance(detalhes, dict):
        return "", ""
    mensagem = str(detalhes.get("message", ""))[:500]
    if chave:
        mensagem = mensagem.replace(chave, "[redigida]")
    return str(detalhes.get("status", "")), mensagem


def _mensagem_erro_gemini(codigo_http, status_api=""):
    identificador = f" HTTP {codigo_http}"
    if status_api:
        identificador += f" ({status_api})"
    if codigo_http in {401, 403}:
        return (
            f"O Google recusou a chave ou a permissão da API ({identificador}). "
            "Confira a chave e se a Gemini API está habilitada para o projeto."
        )
    if codigo_http == 429:
        return (
            f"O limite ou a cota da Gemini API foi atingido ({identificador}). "
            "Confira os limites de uso do projeto no Google AI Studio."
        )
    if codigo_http == 404:
        return (
            f"O modelo configurado não foi encontrado pela Gemini API ({identificador}). "
            "Confira GEMINI_MODEL."
        )
    if codigo_http is not None and codigo_http >= 500:
        return (
            f"A Gemini API está temporariamente indisponível ({identificador}). "
            "Tente novamente mais tarde."
        )
    return (
        f"A Gemini API rejeitou a solicitação ({identificador}). "
        "Consulte o log do servidor para ver o motivo informado pelo Google."
    )


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
            "estatisticas": _estatisticas_ficha(item["ficha__estrutura_json"]),
        }
        for item in faltosos
    ]
    prompt = (
        "Você interpreta personagens de jogadores ausentes em uma sessão de RPG. "
        "Responda apenas em português brasileiro, de forma coerente com cada ficha, "
        "contexto da cena e personalidade. Seja objetivo: respeite exatamente o comando "
        "do mestre e não acrescente ações, viagens ou decisões não pedidas. "
        "Quando a cena exigir atuação narrativa, responda como o comportamento curto do personagem; "
        "quando o mestre pedir explicação, regras, resumo ou disser 'saia do personagem', "
        "responda como narrador/assistente, com clareza fora da narrativa. "
        "Não invente mudanças permanentes sem dados. "
        "Use exclusivamente os nomes informados em 'nome' para os personagens e não atribua "
        "ações ou estatísticas a outro personagem. Use os campos 'estatisticas' como estado "
        "verificável da ficha; não altere PV, atributos, contadores, itens ou condições sem "
        "uma ação explícita do mestre ou uma conclusão clara da cena. "
        f"Rolagens estão {'permitidas neste comando' if pedido_rolagem(comando) else 'proibidas neste comando'}: "
        "só inclua testes em 'rolagens' quando houver pedido explícito de rolar, jogar dados ou fazer teste. "
        "Se houver vários testes ou dados diferentes, inclua uma entrada distinta para cada teste solicitado. "
        "Não invente um teste quando o comando não pedir. "
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
    nomes_faltosos = {item["ficha__nome"].strip() for item in faltosos}
    pode_rolar = pedido_rolagem(comando)
    modo_fora_personagem = pedido_fora_personagem(comando)
    for saida in saidas:
        if not isinstance(saida, dict):
            continue
        personagem = str(saida.get("personagem", "")).strip()
        if modo_fora_personagem:
            personagem = "Narrador"
        elif personagem not in nomes_faltosos and personagem not in {"Narrador", "Sistema"}:
            personagem = context_name(faltosos)
        saida["personagem"] = personagem
        texto_saida = saida.get("texto")
        if texto_saida is None:
            texto_saida = saida.get("mensagem", "")
        saida["texto"] = str(texto_saida)[:8000]
        rolagens_solicitadas = saida.get("rolagens") or []
        saida["rolagens"] = []
        if pode_rolar:
            rolagens = [
                _executar_rolagem(rolagem)
                for rolagem in rolagens_solicitadas
                if isinstance(rolagem, dict)
            ]
            saida["rolagens"] = rolagens
            for rolagem in rolagens:
                saida["texto"] = formatar_rolagem_no_texto(
                    saida["texto"],
                    rolagem,
                )
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
    try:
        dificuldade = rolagem.get("dificuldade")
        if dificuldade is not None:
            dificuldade = int(dificuldade)
        return _rolar(
            rolagem.get("quantidade", 1),
            rolagem.get("dados", 20),
            dificuldade,
            bool(rolagem.get("explosao")),
        ) | {"teste": str(rolagem.get("teste", "Teste"))[:160]}
    except (TypeError, ValueError, OverflowError):
        return {
            "teste": str(rolagem.get("teste", "Teste"))[:160],
            "dados": 20,
            "quantidade": 1,
            "resultados": [],
            "dificuldade": None,
            "sucessos": None,
            "explosao": False,
            "erro": "Parâmetros de rolagem inválidos.",
        }


def _estatisticas_ficha(estrutura):
    estatisticas = []
    if not isinstance(estrutura, dict):
        return estatisticas

    def visitar(valor):
        if isinstance(valor, dict):
            rotulo = valor.get("rotulo") or valor.get("nomeAtributo") or valor.get("titulo")
            campos_valor = [
                chave for chave in (
                    "valorAtributo",
                    "valorGrande",
                    "valorPequeno",
                    "valorBase",
                    "valorBonus",
                    "valorOutros",
                    "valorAtual",
                    "valorMaximo",
                )
                if chave in valor
            ]
            if rotulo and campos_valor:
                estatisticas.append({
                    "rotulo": rotulo,
                    "valores": {chave: valor[chave] for chave in campos_valor},
                })
            for chave, conteudo in valor.items():
                if chave not in {"rotulo", "nomeAtributo", "titulo"}:
                    visitar(conteudo)
        elif isinstance(valor, list):
            for conteudo in valor:
                visitar(conteudo)

    visitar(estrutura)
    return estatisticas


def pedido_rolagem(comando):
    texto = comando.lower()
    padroes = (
        r"\brol[ae]r?\b",
        r"\brolagem\b",
        r"\bteste[s]?\b",
        r"\bjogue?\b",
        r"\btir(?:e|ar|a)\b",
        r"\bd(?:4|6|8|10|12|20|100)\b",
        r"\b\d+d\d+\b",
        r"\bdados\b",
        r"\bchance[s]?\b",
        r"\bdificuldade\b",
    )
    return any(re.search(padrao, texto) for padrao in padroes)


def pedido_fora_personagem(comando):
    texto = comando.lower()
    padroes = (
        r"\bsaia do personagem\b",
        r"\bfora do personagem\b",
        r"\bsem interpretar\b",
        r"\bcomo (?:ia|assistente|narrador|mestre)\b",
        r"\bmodo (?:narrador|mestre|analise|análise)\b",
        r"\bexplique (?:a mecânica|as regras|o sistema)\b",
    )
    return any(re.search(padrao, texto) for padrao in padroes)


def formatar_rolagem_no_texto(texto, rolagem):
    partes = [str(rolagem.get("teste") or "Teste")]
    if rolagem.get("erro"):
        partes.append(str(rolagem["erro"]))
    else:
        partes.append(f"d{rolagem.get('dados', 20)}")
        resultados = rolagem.get("resultados") or []
        partes.append(f"resultados [{', '.join(str(valor) for valor in resultados)}]")
        if rolagem.get("sucessos") is not None:
            partes.append(f"{rolagem['sucessos']} sucesso(s)")
    resultado = " — ".join(partes)
    texto_limpo = str(texto or "").strip()
    return f"{texto_limpo}\n{resultado}".strip() if texto_limpo else resultado


def estado_ficha_para_relatorio(estrutura):
    if not isinstance(estrutura, dict):
        return {}
    estado = {}
    for numero, coluna in sorted(
        ((int(chave), valor) for chave, valor in estrutura.get("colunas", {}).items()
         if str(chave).isdigit() and isinstance(valor, dict)),
        key=lambda item: item[0],
    ):
        abas = []
        for aba in coluna.get("abas", []):
            if not isinstance(aba, dict):
                continue
            secoes = []
            for secao in aba.get("secoes", []):
                if not isinstance(secao, dict):
                    continue
                componentes = []
                for componente in secao.get("componentes", []):
                    if not isinstance(componente, dict):
                        continue
                    componentes.append(componente)
                secoes.append({
                    "titulo": secao.get("titulo"),
                    "tipo": secao.get("tipo"),
                    "componentes": componentes,
                })
            abas.append({
                "titulo": aba.get("titulo"),
                "secoes": secoes,
            })
        estado[str(numero)] = {"ativa": coluna.get("ativa", True), "abas": abas}
    return estado


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
            "estado_atual": estado_ficha_para_relatorio(item["ficha__estrutura_json"]),
        }
        for item in faltosos
    ]
    prompt = (
        "Resuma a sessão de cada personagem ausente no formato JSON desta forma: "
        '{"personagens":[{"personagem":"nome","resumo":"texto corrido",'
        '"revisao":[{"titulo":"Itens/Coletáveis","acoes":["ação + componente + contexto"]}],'
        '"veredito":"sensação ou estado ao fim da sessão"}]}. '
        "Use português brasileiro e contabilize exclusivamente mudanças descritas na conversa "
        "que correspondam a componentes presentes na ficha atual. "
        "Para cada perda ou ganho de PV, mana, determinação, ímpeto ou outro atributo/contador, "
        "informe o componente, a variação e o estado atual ou final conhecido. "
        "Para condições, lesões, traumas, itens guardados, gastos, recebidos, perdidos ou quebrados, "
        "use o título correspondente à ficha e descreva cada mudança com ação + componente + contexto. "
        "Não invente valores, condições ou itens que não estejam na conversa ou na ficha. "
        "Não repita informações sem mudança. Use títulos diferentes quando necessário; "
        "não adote um padrão fixo de títulos além da estrutura real da ficha. "
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
    nomes_faltosos = {ficha["nome"].strip() for ficha in fichas}
    personagens_normalizados = []
    for personagem in resultado.get("personagens", []):
        if not isinstance(personagem, dict):
            continue
        nome = str(personagem.get("personagem", "")).strip()
        if nome not in nomes_faltosos:
            nome = next(
                (ficha["nome"] for ficha in fichas if ficha["nome"].strip().lower() == nome.lower()),
                "",
            )
        if not nome:
            continue
        personagem["personagem"] = nome
        personagem["resumo"] = str(personagem.get("resumo", ""))[:8000]
        personagem["veredito"] = str(personagem.get("veredito", ""))[:2000]
        revisoes = personagem.get("revisao")
        personagem["revisao"] = revisoes if isinstance(revisoes, list) else []
        personagens_normalizados.append(personagem)
    resultado["personagens"] = personagens_normalizados
    sessao.relatorio_json = resultado
    sessao.save(update_fields=["relatorio_json"])
    return resultado
