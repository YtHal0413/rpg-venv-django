import json

from django.core.exceptions import ValidationError


TIPOS_COMPONENTE = {
    "AtributoSimples",
    "AtributoDuplo",
    "AtributoComplexo",
    "Contador",
    "Checkbox",
    "InformacaoCurta",
    "AnotacaoSimples",
    "AnotacaoCheckbox",
    "AnotacaoDetalhada",
}
TAMANHO_MAXIMO_ESTRUTURA = 1_000_000
MAXIMO_ELEMENTOS_FICHA = 3000
MAXIMO_COMPONENTES_SECAO = 250
_proximo_id = 1000


def _texto(valor, campo, limite):
    if not isinstance(valor, str):
        raise ValidationError(f"O campo {campo} deve ser texto.")
    if len(valor) > limite:
        raise ValidationError(f"O campo {campo} excede o limite de caracteres.")
    return valor


def _inteiro(valor, campo, minimo=-1_000_000, maximo=1_000_000):
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValidationError(f"O campo {campo} deve ser um número inteiro.")
    if not minimo <= valor <= maximo:
        raise ValidationError(f"O campo {campo} está fora do limite permitido.")
    return valor


def _id(valor, ids, gerador):
    if valor is None:
        valor = gerador()
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
        raise ValidationError("A estrutura contém um identificador inválido.")
    if valor in ids:
        raise ValidationError("A estrutura contém identificadores duplicados.")
    ids.add(valor)
    return valor


def _novo_id():
    global _proximo_id
    _proximo_id += 1
    return _proximo_id


def _normalizar_componente(componente, tipo, ids):
    if not isinstance(componente, dict):
        raise ValidationError("Os componentes da ficha devem ser objetos.")
    if tipo not in TIPOS_COMPONENTE:
        raise ValidationError("A ficha contém um tipo de componente inválido.")
    resultado = {"id": _id(componente.get("id"), ids, _novo_id)}

    campos_texto = {
        "rotulo": 160,
        "nomeAtributo": 160,
        "campoTexto": 2000,
        "descricao": 10000,
        "subtituloAnotacao": 500,
        "anotacaoExtra": 2000,
    }
    campos_inteiros = {
        "valorAtributo",
        "valorGrande",
        "valorPequeno",
        "valorBase",
        "valorBonus",
        "valorOutros",
        "valorAtual",
        "valorMaximo",
        "criterioOrdenacao",
    }
    for campo, limite in campos_texto.items():
        if campo in componente:
            resultado[campo] = _texto(componente[campo], campo, limite)
    for campo in campos_inteiros:
        if campo in componente:
            resultado[campo] = _inteiro(componente[campo], campo)
    for campo in ("estaMarcado",):
        if campo in componente:
            if not isinstance(componente[campo], bool):
                raise ValidationError(f"O campo {campo} deve ser verdadeiro ou falso.")
            resultado[campo] = componente[campo]

    cor = componente.get("corSeletor", "#4A4E69")
    if not isinstance(cor, str) or len(cor) > 32:
        raise ValidationError("A cor do contador é inválida.")
    resultado["corSeletor"] = cor
    return resultado


def validar_estrutura_ficha(dados):
    """Valida limites, campos e IDs antes de persistir a estrutura JSON."""
    if not isinstance(dados, dict):
        raise ValidationError("A estrutura da ficha deve ser um objeto JSON.")
    try:
        tamanho = len(json.dumps(dados, ensure_ascii=False))
    except (TypeError, ValueError) as error:
        raise ValidationError("A estrutura da ficha não é um JSON válido.") from error
    if tamanho > TAMANHO_MAXIMO_ESTRUTURA:
        raise ValidationError("A estrutura da ficha excede o tamanho permitido.")

    visibilidade = dados.get("visibilidade", "todos")
    if visibilidade not in {"todos", "mestres"}:
        raise ValidationError("A visibilidade informada é inválida.")
    colunas = dados.get("colunas")
    if not isinstance(colunas, dict) or len(colunas) > 3:
        raise ValidationError("A ficha deve conter no máximo três colunas.")

    ids = set()
    elementos = 0
    estrutura = {"visibilidade": visibilidade, "colunas": {}}
    for numero in range(1, 4):
        chave = str(numero)
        coluna = colunas.get(chave, {})
        if not isinstance(coluna, dict):
            raise ValidationError("A configuração da coluna é inválida.")
        abas = coluna.get("abas", [])
        if not isinstance(abas, list) or len(abas) > 3:
            raise ValidationError("Cada coluna pode conter no máximo três abas.")

        abas_normalizadas = []
        for aba in abas:
            if not isinstance(aba, dict):
                raise ValidationError("As abas da ficha devem ser objetos.")
            elementos += 1
            secoes = aba.get("secoes", [])
            if not isinstance(secoes, list):
                raise ValidationError("As seções da aba devem ser uma lista.")
            secoes_normalizadas = []
            for secao in secoes:
                if not isinstance(secao, dict):
                    raise ValidationError("As seções da ficha devem ser objetos.")
                tipo = secao.get("tipo")
                if tipo not in TIPOS_COMPONENTE:
                    raise ValidationError("A seção contém um tipo de componente inválido.")
                componentes = secao.get("componentes", [])
                if (
                    not isinstance(componentes, list)
                    or len(componentes) > MAXIMO_COMPONENTES_SECAO
                ):
                    raise ValidationError("A seção excede o limite de componentes.")
                elementos += 1 + len(componentes)
                secao_normalizada = {
                    "id": _id(secao.get("id"), ids, _novo_id),
                    "titulo": _texto(secao.get("titulo", "Nova Seção"), "título", 100),
                    "tipo": tipo,
                    "componentes": [
                        _normalizar_componente(componente, tipo, ids)
                        for componente in componentes
                    ],
                }
                secoes_normalizadas.append(secao_normalizada)

            aba_id = _id(aba.get("id"), ids, _novo_id)
            abas_normalizadas.append(
                {
                    "id": aba_id,
                    "titulo": _texto(aba.get("titulo", "Nova Aba"), "título", 80),
                    "ehPadrao": bool(aba.get("ehPadrao", False)),
                    "secoes": secoes_normalizadas,
                }
            )

        if numero == 1 and not any(
            aba["ehPadrao"] or aba["titulo"] == "Geral"
            for aba in abas_normalizadas
        ):
            if len(abas_normalizadas) < 3:
                abas_normalizadas.insert(
                    0,
                    {
                        "id": _id(None, ids, _novo_id),
                        "titulo": "Geral",
                        "ehPadrao": True,
                        "secoes": [],
                    },
                )
                elementos += 1
            elif abas_normalizadas:
                abas_normalizadas[0]["ehPadrao"] = True
        elif numero == 1 and abas_normalizadas:
            padrao = next(
                (
                    aba
                    for aba in abas_normalizadas
                    if aba["ehPadrao"] or aba["titulo"] == "Geral"
                ),
                abas_normalizadas[0],
            )
            padrao["ehPadrao"] = True

        if elementos > MAXIMO_ELEMENTOS_FICHA:
            raise ValidationError("A ficha excede o limite de elementos.")
        aba_ativa = coluna.get("abaAtivaId")
        if aba_ativa not in {aba["id"] for aba in abas_normalizadas}:
            aba_ativa = abas_normalizadas[0]["id"] if abas_normalizadas else None
        estrutura["colunas"][chave] = {
            "ativa": bool(coluna.get("ativa", True)),
            "abaAtivaId": aba_ativa,
            "abas": abas_normalizadas,
        }

    return estrutura


def proximo_id_estrutura(estrutura):
    ids = []
    for coluna in estrutura.get("colunas", {}).values():
        for aba in coluna.get("abas", []):
            ids.append(aba.get("id", 0))
            for secao in aba.get("secoes", []):
                ids.append(secao.get("id", 0))
                ids.extend(
                    componente.get("id", 0)
                    for componente in secao.get("componentes", [])
                )
    return max(ids, default=1000) + 1


def renovar_ids_estrutura(estrutura):
    novo = json.loads(json.dumps(estrutura))
    proximo = proximo_id_estrutura(novo)
    for coluna in novo.get("colunas", {}).values():
        aba_ativa_anterior = coluna.get("abaAtivaId")
        for aba in coluna.get("abas", []):
            aba_anterior = aba["id"]
            aba["id"] = proximo
            proximo += 1
            for secao in aba.get("secoes", []):
                secao["id"] = proximo
                proximo += 1
                for componente in secao.get("componentes", []):
                    componente["id"] = proximo
                    proximo += 1
            if aba_ativa_anterior == aba_anterior:
                coluna["abaAtivaId"] = aba["id"]
    return novo
