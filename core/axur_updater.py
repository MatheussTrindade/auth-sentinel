"""
Atualiza o status das detecções na Axur (Exposure API) com base no
resultado da validação:

    VÁLIDO   -> IN_TREATMENT  (equipe entra e trata)
    INVÁLIDO -> DISCARDED     (credencial não funciona mais)
    ERRO:*   -> não mexe      (fica NEW, validação manual caso a caso)

Endpoint: PATCH /exposure-api/{exposureCategory}/{id}
Doc: openapi-axur.yaml, operationId "updateDetection"
Só existe versão por-detecção (o endpoint em lote da Axur só aceita o
campo "tags", não "status").
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from core.axur_client import AXUR_API_BASE, AXUR_API_TOKEN, AxurAPIError


STATUS_MAP = {
    "VÁLIDO": "IN_TREATMENT",
    "INVÁLIDO": "DISCARDED",
}


@dataclass
class AxurUpdateResult:
    detection_id: str
    novo_status: str
    ok: bool
    erro: str = ""


def _session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    return s


def _status_alvo(resultado_validacao: str) -> str | None:
    """Retorna o status da Axur correspondente, ou None se for pra pular (ERRO:*)."""
    return STATUS_MAP.get(resultado_validacao)


def _atualizar_uma(session: requests.Session, base_url: str, detection_id: str,
                    novo_status: str, tentativas: int = 5) -> AxurUpdateResult:
    url = f"{base_url}/exposure-api/credentials/{detection_id}"
    payload = {"field": "status", "value": novo_status}

    for tentativa in range(1, tentativas + 1):
        resp = session.patch(url, json=payload, timeout=30)

        if resp.status_code == 204:
            return AxurUpdateResult(detection_id, novo_status, ok=True)

        if resp.status_code == 429:
            # Rate limit — respeita Retry-After se a API mandar, senão backoff exponencial
            espera = resp.headers.get("Retry-After")
            espera = float(espera) if espera else min(2 ** tentativa, 30)
            time.sleep(espera)
            continue

        if resp.status_code == 401:
            return AxurUpdateResult(detection_id, novo_status, ok=False, erro="token inválido/expirado (401)")

        return AxurUpdateResult(detection_id, novo_status, ok=False,
                                 erro=f"{resp.status_code}: {resp.text[:150]}")

    return AxurUpdateResult(detection_id, novo_status, ok=False, erro="rate limit persistente (429)")


def atualizar_status_no_painel(resultados: list[dict], token: str | None = None,
                                base_url: str | None = None,
                                pausa_entre_requests: float = 0.35) -> list[AxurUpdateResult]:
    """
    Recebe a lista de resultados do validator.py (cada um já com
    "status" e "axur_detection_id") e atualiza cada detecção na Axur.

    Resultados sem axur_detection_id (vieram de CSV manual, não da API)
    ou com status ERRO:* são pulados silenciosamente.

    pausa_entre_requests: intervalo (s) entre PATCHs consecutivos, pra não
    estourar o rate limit da Axur logo de cara — não existe endpoint em
    lote pra "status", então isso é sempre 1 request por detecção.
    """
    token = token or AXUR_API_TOKEN
    base_url = base_url or AXUR_API_BASE
    if not token:
        raise AxurAPIError("AXUR_API_TOKEN não configurado.")

    session = _session(token)
    pendentes = [
        (r["axur_detection_id"], _status_alvo(r["status"]))
        for r in resultados
        if r.get("axur_detection_id") and _status_alvo(r["status"]) is not None
    ]

    atualizacoes: list[AxurUpdateResult] = []
    for detection_id, novo_status in pendentes:
        atualizacoes.append(_atualizar_uma(session, base_url, detection_id, novo_status))
        time.sleep(pausa_entre_requests)

    # Segunda passada só pros que ainda falharam por rate limit — dá mais
    # tempo pro limite da Axur "esfriar" antes de tentar de novo.
    indices_429 = [i for i, a in enumerate(atualizacoes) if not a.ok and "429" in a.erro]
    if indices_429:
        time.sleep(10)
        for i in indices_429:
            atualizacoes[i] = _atualizar_uma(session, base_url,
                                              atualizacoes[i].detection_id,
                                              atualizacoes[i].novo_status)
            time.sleep(pausa_entre_requests)

    return atualizacoes