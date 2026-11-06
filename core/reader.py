"""
Leitura e normalização do CSV de credenciais.
Suporta delimitadores ; e , e múltiplos encodings.
"""

import csv
import re
from pathlib import Path
from urllib.parse import urlparse


ENCODINGS = ["utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1"]


def _abrir_arquivo(path: Path):
    for enc in ENCODINGS:
        try:
            f = open(path, "r", encoding=enc)
            f.read(2048)
            f.seek(0)
            return f, enc
        except (UnicodeDecodeError, Exception):
            try:
                f.close()
            except Exception:
                pass

    # fallback
    return open(path, "r", encoding="latin-1", errors="replace"), "latin-1-replace"


def _normalizar_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def _extrair_campo(row: dict, *chaves) -> str:
    for chave in chaves:
        valor = row.get(chave, "").strip()
        if valor:
            return valor
    return ""


def ler_csv(path: Path) -> list[dict]:
    """
    Lê o CSV e retorna lista de dicts com:
    login, password, url, host, login_type
    """
    credenciais = []

    f, enc = _abrir_arquivo(path)
    print(f"[*] Encoding detectado: {enc}")

    try:
        sample = f.read(2048)
        f.seek(0)
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        print(f"[*] Delimitador detectado: '{delimiter}'")

        reader = csv.DictReader(f, delimiter=delimiter)

        for i, row in enumerate(reader, start=1):
            # Normalizar chaves
            row = {(k or "").lower().strip(): (v or "").strip() for k, v in row.items()}

            login      = _extrair_campo(row, "login", "username", "email", "user")
            password   = _extrair_campo(row, "password", "senha", "pass")
            url        = _normalizar_url(_extrair_campo(row, "url", "host", "site"))
            login_type = _extrair_campo(row, "login_type", "tipo").lower()

            if not login or not password or not url:
                print(f"  [!] Linha {i} ignorada — campos obrigatórios ausentes")
                continue

            credenciais.append({
                "login":      login,
                "password":   password,
                "url":        url,
                "host":       urlparse(url).netloc,
                "login_type": login_type,
            })

    finally:
        f.close()

    return credenciais
