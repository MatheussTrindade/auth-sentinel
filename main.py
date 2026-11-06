"""
Auth Sentinel — Auditoria de Credenciais
Uso: python main.py credenciais.csv [saida.csv] [--workers 10] [--headless]
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Carrega variáveis do .env (token da Axur etc.) antes de qualquer import que as leia
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich import box
from rich.align import Align

from core.reader import ler_csv
from core.validator import ValidatorPool
from core.axur_client import buscar_novas_identificacoes, AxurAPIError
from core.axur_updater import atualizar_status_no_painel
from reports.generator import gerar_relatorio

console = Console()

BANNER = r"""
 █████╗ ██╗   ██╗████████╗██╗  ██╗    ███████╗███████╗███╗   ██╗████████╗██╗███╗   ██╗███████╗██╗     
██╔══██╗██║   ██║╚══██╔══╝██║  ██║    ██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗  ██║██╔════╝██║     
███████║██║   ██║   ██║   ███████║    ███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔██╗ ██║█████╗  ██║     
██╔══██║██║   ██║   ██║   ██╔══██║    ╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╗██║██╔══╝  ██║     
    ██║  ██║╚██████╔╝   ██║   ██║  ██║    ███████║███████╗██║ ╚████║   ██║   ██║██║ ╚████║███████╗███████╗
    ╚═╝  ╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝    ╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝
"""

def exibir_banner():
    console.print()
    console.print(Text(BANNER, style="bold yellow"), justify="center")
    console.print(
        Align.center(
            Text("[ Credential Audit Tool — Cybersecurity ]", style="bold green")
        )
    )
    console.print(
        Align.center(
            Text("by auth-sentinel v1.0.0", style="dim white")
        )
    )
    console.print()

def parse_args():
    parser = argparse.ArgumentParser(description="Validador de credenciais para auditoria")
    parser.add_argument("input", nargs="?", help="CSV de entrada (login;password;url)")
    parser.add_argument("--from-axur", action="store_true",
                         help="Busca as novas identificações direto na API da Axur, em vez de ler um CSV")
    parser.add_argument("--update-axur", action="store_true",
                         help="Depois de validar, atualiza o status de cada detecção no painel da Axur "
                              "(VÁLIDO -> IN_TREATMENT, INVÁLIDO -> DISCARDED, ERRO -> mantém NEW). "
                              "Só tem efeito junto com --from-axur.")
    parser.add_argument("output", nargs="?", default="relatorio_auditoria.csv", help="CSV de saída")
    parser.add_argument("--workers", type=int, default=10, help="Número de workers paralelos (default: 10)")
    parser.add_argument("--headless", action="store_true", default=True, help="Rodar sem abrir janela do browser")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout por tentativa em segundos (default: 30)")
    return parser.parse_args()


async def main():
    exibir_banner()

    args = parse_args()

    # 1. Obter credenciais — via Axur API ou via CSV
    if args.from_axur:
        console.print("[bold cyan][*][/bold cyan] Buscando novas identificações na API da Axur...")
        try:
            creds = buscar_novas_identificacoes()
        except AxurAPIError as e:
            console.print(f"[bold red][ERRO][/bold red] {e}")
            sys.exit(1)
    else:
        if not args.input:
            console.print("[bold red][ERRO][/bold red] Informe um CSV de entrada ou use --from-axur")
            sys.exit(1)
        input_path = Path(args.input)
        if not input_path.exists():
            console.print(f"[bold red][ERRO][/bold red] Arquivo não encontrado: {input_path}")
            sys.exit(1)
        console.print(f"[bold cyan][*][/bold cyan] Lendo credenciais de: [white]{input_path}[/white]")
        creds = ler_csv(input_path)

    if not creds:
        console.print("[bold red][ERRO][/bold red] Nenhuma credencial válida encontrada no CSV.")
        sys.exit(1)

    # Info panel
    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold yellow")
    info.add_column(style="white")
    info.add_row("Credenciais carregadas", str(len(creds)))
    info.add_row("Workers paralelos", str(args.workers))
    info.add_row("Timeout por tentativa", f"{args.timeout}s")
    info.add_row("Saída", str(args.output))

    console.print(Panel(info, title="[bold yellow]⚙  Configuração[/bold yellow]", border_style="yellow", box=box.ROUNDED))
    console.print()

    # 2. Validar com progress bar
    pool = ValidatorPool(
        workers=args.workers,
        headless=args.headless,
        timeout=args.timeout,
    )

    console.print("[bold cyan][*][/bold cyan] Iniciando validação...\n")

    with Progress(
        SpinnerColumn(style="yellow"),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=40, style="yellow", complete_style="green"),
        TextColumn("[bold green]{task.completed}[/bold green]/[white]{task.total}[/white]"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Validando credenciais...", total=len(creds))
        resultados = await pool.run(creds, progress=progress, task=task)

    # 3. Relatório
    output_path = Path(args.output)
    gerar_relatorio(resultados, output_path)

    # 4. Resumo final
    validos   = [r for r in resultados if r["status"] == "VÁLIDO"]
    invalidos = [r for r in resultados if r["status"] == "INVÁLIDO"]
    erros     = [r for r in resultados if r["status"].startswith("ERRO")]

    tabela = Table(box=box.ROUNDED, border_style="yellow", show_header=True, header_style="bold yellow")
    tabela.add_column("Métrica", style="bold white")
    tabela.add_column("Valor", justify="right")

    tabela.add_row("Total testado",    f"[white]{len(resultados)}[/white]")
    tabela.add_row("✅ Válidos",       f"[bold green]{len(validos)}[/bold green]")
    tabela.add_row("❌ Inválidos",     f"[bold red]{len(invalidos)}[/bold red]")
    tabela.add_row("⚠️  Erros",         f"[bold yellow]{len(erros)}[/bold yellow]")
    tabela.add_row("📄 Relatório",     f"[dim white]{output_path.resolve()}[/dim white]")

    console.print()
    console.print(Panel(tabela, title="[bold yellow]📊  Resumo Final[/bold yellow]", border_style="yellow", box=box.ROUNDED))
    console.print()

    if validos:
        t = Table(box=box.SIMPLE, border_style="green", show_header=True, header_style="bold green")
        t.add_column("Host")
        t.add_column("Login")
        t.add_column("Status")
        for r in validos:
            t.add_row(r["host"], r["login"], "[bold green]VÁLIDO[/bold green]")
        console.print(Panel(t, title="[bold green]✅  Credenciais Válidas[/bold green]", border_style="green", box=box.ROUNDED))

    # 5. Atualizar status no painel da Axur (opcional)
    if args.update_axur:
        if not args.from_axur:
            console.print("[bold yellow][!][/bold yellow] --update-axur ignorado: só funciona junto com --from-axur "
                           "(resultados de CSV não têm detection_id pra atualizar).")
        else:
            console.print("\n[bold cyan][*][/bold cyan] Atualizando status no painel da Axur...")
            try:
                atualizacoes = atualizar_status_no_painel(resultados)
            except AxurAPIError as e:
                console.print(f"[bold red][ERRO][/bold red] {e}")
                sys.exit(1)

            ok = [a for a in atualizacoes if a.ok]
            falhas = [a for a in atualizacoes if not a.ok]

            console.print(f"  [green]{len(ok)}[/green] detecções atualizadas com sucesso.")
            if falhas:
                console.print(f"  [bold red]{len(falhas)}[/bold red] falharam:")
                for f in falhas:
                    console.print(f"    [red]•[/red] {f.detection_id} -> {f.novo_status}: {f.erro}")

            pulados = len(resultados) - len(atualizacoes)
            if pulados:
                console.print(f"  [dim]{pulados} resultado(s) com ERRO:* — mantidos como NEW, sem alteração no painel.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())