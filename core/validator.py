"""
Validação de credenciais com Playwright + asyncio.
Suporta N workers em paralelo com semáforo de controle.
"""

import asyncio
import re
from datetime import datetime

from playwright.async_api import async_playwright, Page, BrowserContext

# URLs que indicam login bem-sucedido
URLS_SUCESSO = [
    "dashboard", "home", "painel", "perfil",
    "cliente", "selecionar-perfil", "inicio", "welcome",
]

# Textos na página que indicam login bem-sucedido
TEXTOS_SUCESSO = [
    "logout", "sair", "minha conta", "bem-vindo",
    "bem vindo", "meu perfil", "sign out",
]

# Seletores de campo de login (ordem de prioridade)
SELETORES_LOGIN = [
    "input[data-testid='field-login']",
    "input[name='username']",
    "input[name='user']",
    "input[name='email']",
    "input[type='email']",
    "input[placeholder*='CPF' i]",
    "input[placeholder*='usuário' i]",
    "input[placeholder*='email' i]",
    "input[type='text']",
]

# Seletores de campo de senha
SELETORES_SENHA = [
    "input[data-testid='field-password']",
    "input[name='password']",
    "input[name='pass']",
    "input[name='senha']",
    "input[type='password']",
]

# Seletores de botão de submit
SELETORES_SUBMIT = [
    "button[type='submit']",
    "input[type='submit']",
    "button.btn-primary",
    "button.btn-login",
]

TEXTOS_SUBMIT = ["entrar", "acessar", "login", "logar", "sign in", "entrar agora"]


def extrair_digits(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


class ValidatorPool:
    def __init__(self, workers: int = 10, headless: bool = True, timeout: int = 30):
        self.workers = workers
        self.headless = headless
        self.timeout = timeout * 1000  # Playwright usa ms

   # Substitua o método run inteiro por este no core/validator.py

    async def run(self, creds: list[dict], progress=None, task=None) -> list[dict]:
        semaforo = asyncio.Semaphore(self.workers)
        resultados = []
        lock = asyncio.Lock()

        total = len(creds)
        contador = {"n": 0}

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-notifications",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            async def testar(cred: dict):
                async with semaforo:
                    resultado = await self._testar_cred(browser, cred)

                    if resultado is None:
                        resultado = self._resultado(cred, "ERRO: resultado inesperado")

                    async with lock:
                        contador["n"] += 1
                        if progress and task is not None:
                            progress.advance(task)

                        emoji = "✅" if resultado["status"] == "VÁLIDO" else (
                            "❌" if resultado["status"] == "INVÁLIDO" else "⚠️ "
                        )
                        # Print colorido via rich se disponível
                        try:
                            from rich.console import Console
                            c = Console()
                            status_fmt = (
                                f"[bold green]{resultado['status']}[/bold green]"
                                if resultado["status"] == "VÁLIDO"
                                else f"[bold red]{resultado['status']}[/bold red]"
                                if resultado["status"] == "INVÁLIDO"
                                else f"[bold yellow]{resultado['status']}[/bold yellow]"
                            )
                            c.print(
                                f"  {emoji} [dim]{contador['n']:>4}/{total}[/dim]  "
                                f"[cyan]{resultado['host']:<30}[/cyan]  "
                                f"[white]{resultado['login']:<30}[/white]  "
                                f"{status_fmt}"
                            )
                        except Exception:
                            print(f"  [{contador['n']:>4}/{total}] {emoji}  {resultado['host']:<30}  {resultado['login']:<30}  {resultado['status']}")

                        resultados.append(resultado)

            tasks = [testar(c) for c in creds]
            await asyncio.gather(*tasks)

            await browser.close()

        return resultados

    async def _testar_cred(self, browser, cred: dict) -> dict:
        contexto: BrowserContext = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            permissions=["notifications", "geolocation", "local-network-access"],
            ignore_https_errors=True,
        )

        page: Page = await contexto.new_page()

        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        try:
            # 1. Acessar URL
            await page.goto(cred["url"], timeout=self.timeout, wait_until="domcontentloaded")

            # 1.5 networkidle opcional — ignora timeout
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            # 1.6 Permissão de rede local via CDP
            try:
                cdp = await contexto.new_cdp_session(page)
                await cdp.send("Browser.setPermission", {
                    "permission": {"name": "local-network-access"},
                    "setting": "granted",
                    "origin": page.url,
                })
            except Exception:
                pass

            # 2. Fechar popups
            await self._fechar_popups(page)

            # 3. Localizar campos
            campo_login = await self._encontrar_campo(page, SELETORES_LOGIN)
            campo_senha = await self._encontrar_campo(page, SELETORES_SENHA)

            if not campo_login or not campo_senha:
                return self._resultado(cred, "ERRO: campos de login não encontrados")

            # 4. Preencher login
            login = cred["login"]
            if cred.get("login_type") == "cpf":
                login = extrair_digits(login)

            await campo_login.click()
            await campo_login.fill("")
            await campo_login.type(login, delay=50)

            # 5. Preencher senha
            await campo_senha.click()
            await campo_senha.fill("")
            await campo_senha.type(cred["password"], delay=50)

            # 6. Submeter
            url_antes = page.url
            submetido = await self._submeter(page)

            if not submetido:
                await campo_senha.press("Enter")

            # 7. Aguardar resposta
            try:
                await page.wait_for_url(lambda url: url != url_antes, timeout=15000)
            except Exception:
                pass

            await asyncio.sleep(1.5)

            # 8. Validar resultado
            valido = self._checar_sucesso(page.url)

            if not valido:
                conteudo = await page.content()
                valido = self._checar_textos(conteudo)

            status = "VÁLIDO" if valido else "INVÁLIDO"
            return self._resultado(cred, status)

        except Exception as e:
            return self._resultado(cred, f"ERRO: {type(e).__name__}: {str(e)[:80]}")

        finally:
            try:
                await contexto.close()
            except Exception:
                pass

    async def _encontrar_campo(self, page: Page, seletores: list[str]):
        for seletor in seletores:
            try:
                el = await page.wait_for_selector(seletor, state="visible", timeout=5000)
                if el:
                    return page.locator(seletor).first
            except Exception:
                continue
        return None

    async def _fechar_popups(self, page: Page):
    # Conceder permissão de rede local via CDP
        try:
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("Browser.setPermission", {
                "permission": {"name": "local-network-access"},
                "setting": "granted",
                "origin": page.url,
            })
        except Exception:
            pass

        # Tentar clicar botões de aceitar/permitir
        try:
            botoes = await page.query_selector_all("button, [role='button']")
            for botao in botoes:
                texto = (await botao.inner_text()).strip().lower()
                if any(t in texto for t in ["permitir", "allow", "aceitar", "accept", "ok", "concordo"]):
                    if await botao.is_visible():
                        await botao.click()
                        await asyncio.sleep(0.5)
                        break
        except Exception:
            pass

        # ESC para fechar modais
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

    async def _submeter(self, page: Page) -> bool:
        # Tentar seletores diretos
        for seletor in SELETORES_SUBMIT:
            try:
                btn = page.locator(seletor).first
                if await btn.is_visible(timeout=2000) and await btn.is_enabled():
                    await btn.click()
                    return True
            except Exception:
                continue

        # Tentar por texto
        try:
            botoes = await page.query_selector_all("button")
            for btn in botoes:
                texto = (await btn.inner_text()).strip().lower()
                if any(t in texto for t in TEXTOS_SUBMIT):
                    if await btn.is_visible() and await btn.is_enabled():
                        await btn.click()
                        return True
        except Exception:
            pass

        return False

    def _checar_sucesso(self, url: str) -> bool:
        url_lower = url.lower()
        return any(palavra in url_lower for palavra in URLS_SUCESSO)

    def _checar_textos(self, conteudo: str) -> bool:
        conteudo_lower = conteudo.lower()
        return any(texto in conteudo_lower for texto in TEXTOS_SUCESSO)

    def _resultado(self, cred: dict, status: str) -> dict:
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "host":      cred["host"],
            "login":     cred["login"],
            "password":  cred["password"],
            "url":       cred["url"],
            "status":    status,
            "axur_detection_id": cred.get("axur_detection_id"),
        }