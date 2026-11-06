"""
Cliente da API da Axur (Exposure API) — busca novas detecções de
credenciais expostas e devolve no MESMO formato que core/reader.ler_csv()
produz, para plugar direto no pipeline existente (validator.py,
generator.py) sem alterações.

Endpoint: GET /exposure-api/credentials
Doc: openapi-axur.yaml, seção "Exposure Api Operations"
Auth: header "Authorization: Bearer <API_KEY>" (token estático gerado no
painel da Axur — não é OAuth2 client_credentials).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

import requests


AXUR_API_BASE = os.environ.get("AXUR_API_BASE", "https://api.axur.com/gateway/1.0/api")
AXUR_API_TOKEN = os.environ.get("AXUR_API_TOKEN", "")

# Campos pedidos à API — só o necessário pro validador + rastreio do detection id
DEFAULT_FIELDS = "id,status,user,password,access.host,access.url,created,assets,customer"


class AxurAPIError(Exception):
    pass


@dataclass
class AxurConfig:
    base_url: str = AXUR_API_BASE
    token: str = AXUR_API_TOKEN
    # Detection Status: "NEW", "IN_TREATMENT", "SOLVED" ou "DISCARDED"
    status: str = "NEW"
    fields: str = DEFAULT_FIELDS
    page_size: int = 100
    # opcional: filtra por data de criação, ex. "ge:2025-01-01"
    created: str | None = None
    # obrigatório se o usuário tiver acesso a múltiplos tenants (MSSP)
    customer: str | None = None


def _session(cfg: AxurConfig) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {cfg.token}",
        "Content-Type": "application/json",
    })
    return s


def _normalizar_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def _detection_to_cred(item: dict) -> dict | None:
    """Converte uma detecção da Exposure API no dict que o pipeline espera."""
    login = (item.get("user") or "").strip()
    password = (item.get("password") or "").strip()

    host = (item.get("access.host") or "").strip()
    url = _normalizar_url(host) if host else _normalizar_url(item.get("access.url") or "")

    if not login or not password or not url:
        return None

    return {
        "login": login,
        "password": password,
        "url": url,
        "host": urlparse(url).netloc,
        "login_type": "",
        "axur_detection_id": item.get("id"),
        "axur_access_url_raw": item.get("access.url"),
    }


def buscar_novas_identificacoes(cfg: AxurConfig | None = None) -> list[dict]:
    """
    Busca as detecções de credenciais expostas (status=NEW por padrão) na
    Axur e retorna no formato usado por core/reader.ler_csv().
    """
    cfg = cfg or AxurConfig()
    if not cfg.token:
        raise AxurAPIError(
            "AXUR_API_TOKEN não configurado. Defina a variável de ambiente "
            "ou passe token= no AxurConfig."
        )

    session = _session(cfg)
    credenciais: list[dict] = []

    url = f"{cfg.base_url}/exposure-api/credentials"
    params = {
        "status": cfg.status,
        "fields": cfg.fields,
        "sortBy": "created",
        "order": "asc",
        "pageSize": cfg.page_size,
    }
    if cfg.created:
        params["created"] = cfg.created
    if cfg.customer:
        params["customer"] = cfg.customer

    page = 1
    total = None
    while True:
        params["page"] = page
        resp = session.get(url, params=params, timeout=30)

        if resp.status_code == 401:
            raise AxurAPIError("Token inválido ou expirado (401).")
        if not resp.ok:
            raise AxurAPIError(f"Erro {resp.status_code} ao consultar Axur: {resp.text[:300]}")

        data = resp.json()
        detections = data.get("detections", [])
        total = data.get("pageable", {}).get("total", total)

        if not detections:
            break

        for item in detections:
            cred = _detection_to_cred(item)
            if cred:
                credenciais.append(cred)
            else:
                print(f"  [!] Detecção {item.get('id')} ignorada — campos incompletos (user/password/access.url)")

        if page * cfg.page_size >= (total or 0) or len(detections) < cfg.page_size:
            break
        page += 1

    return credenciais