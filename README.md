# Auth Sentinel — Credential Audit Tool

**Auth Sentinel** is a defensive security tool that automates the validation of
exposed credentials against your organization's login systems. It integrates with
[Axur](https://www.axur.com/) threat intelligence to pull leaked credential
detections, confirms which ones are still valid, and updates the corresponding alert
cards — supporting incident response (password rotation, account lockout, triage).

It drives a real browser (Playwright) to attempt each login in parallel and produces
an audit report of the results.

> **Language note:** This README is in English to reach a broader audience. The CLI
> output and status labels are currently in Portuguese (`VÁLIDO`, `INVÁLIDO`, `ERRO`).

---

## ⚠️ Authorized use & responsibility

This tool tests credentials against login systems. **Use it only against accounts and
systems you are explicitly authorized — in writing — to test** (e.g. internal auditing
of your own organization in response to your employees' leaked credentials).

- Testing credentials against third-party systems without authorization may constitute
  a **crime** (unauthorized access) and violate data-protection laws such as Brazil's
  **LGPD** and the EU **GDPR**.
- The software is provided "as is", without warranty, and the authors are not liable
  for misuse (see [LICENSE](LICENSE)).
- To report a vulnerability in this project, see [SECURITY.md](SECURITY.md).

## 🔐 Data protection

- Credentials (login / password / host) and reports are **personal and sensitive
  data**. Processing must have a lawful basis (e.g. legitimate interest in information
  security) and be limited to incident-response purposes.
- **Secrets** (`AXUR_API_TOKEN`) live in a `.env` file that is never committed. Copy it
  from `.env.example`.
- Reports store the password **masked** (`ab***`). They still contain login/host data —
  treat them as confidential.
- The `.gitignore` blocks `.env`, `input/`, reports, and any root-level `*.csv` / `*.txt`.
  **Never** force-commit these files.
- **Retention:** delete reports once the incident is handled; do not keep them
  indefinitely.

---

## Features

- 🔎 Pulls exposed-credential detections directly from the Axur Exposure API.
- 🌐 Browser-based validation with Playwright (handles JS-rendered login forms).
- ⚡ Parallel validation with a configurable worker pool.
- 🔁 Writes results back to Axur alert cards (`VÁLIDO → IN_TREATMENT`,
  `INVÁLIDO → DISCARDED`, errors left untouched).
- 📄 CSV + human-readable TXT audit reports, with passwords masked.
- 🎨 Rich terminal UI (progress bar and summary tables).

## Requirements

- Python 3.11+
- Google Chromium (installed via Playwright)

## Installation

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install the browser (one time only)
playwright install chromium
```

## Configuration

```bash
cp .env.example .env     # then fill in AXUR_API_TOKEN
```

| Variable          | Required        | Description                                      |
|-------------------|-----------------|--------------------------------------------------|
| `AXUR_API_TOKEN`  | for Axur modes  | Static API token generated in the Axur panel.    |
| `AXUR_API_BASE`   | no              | API base URL (defaults to the public gateway).   |

## Project structure

```
auth-sentinel/
├── main.py                 # Entry point / CLI
├── requirements.txt
├── core/
│   ├── reader.py           # CSV reading and normalization
│   ├── validator.py        # Async validation pool (Playwright)
│   ├── axur_client.py      # Fetch exposed credentials from the Axur API
│   └── axur_updater.py     # Push validation status back to Axur
├── reports/
│   └── generator.py        # CSV + TXT report generation (password masked)
└── input/
    └── exemplo.csv         # Example input CSV (header only)
```

## Usage

### From a CSV file

```bash
# Basic
python main.py input/credentials.csv

# Custom output and 20 workers
python main.py input/credentials.csv report.csv --workers 20

# Longer timeout (slow networks)
python main.py input/credentials.csv --timeout 60
```

### From the Axur API

```bash
# Pull new detections from Axur and validate them
python main.py --from-axur

# Validate and write the result status back to the Axur alert cards
python main.py --from-axur --update-axur
```

### CLI options

| Option          | Default                   | Description                                        |
|-----------------|---------------------------|----------------------------------------------------|
| `input`         | —                         | Input CSV (`login;password;url`).                  |
| `output`        | `relatorio_auditoria.csv` | Output CSV path.                                   |
| `--from-axur`   | off                       | Fetch detections from the Axur API instead of CSV. |
| `--update-axur` | off                       | Write status back to Axur (requires `--from-axur`).|
| `--workers`     | `10`                      | Number of parallel workers.                        |
| `--timeout`     | `30`                      | Per-attempt timeout in seconds.                    |
| `--headless`    | on                        | Run the browser without a visible window.          |

## Input CSV format

```
login;password;url;login_type
user@company.com;password123;https://system.company.com;
11122233344;pass456;https://portal.client.com;cpf
```

Accepted columns (delimiter `;` or `,` is auto-detected):

- **login** — also accepts: `username`, `email`, `user`
- **password** — also accepts: `senha`, `pass`
- **url** — also accepts: `host`, `site`
- **login_type** — optional. Use `cpf` to strip non-digits from the login.

## Output

Two files are generated:

- `relatorio_auditoria.csv` — all results: timestamp, host, login, **masked** password,
  URL, status.
- `relatorio_auditoria.txt` — human-readable audit summary highlighting valid credentials.

## Status values

| Status     | Meaning                                              |
|------------|------------------------------------------------------|
| `VÁLIDO`   | Login succeeded (success URL or on-page text found). |
| `INVÁLIDO` | Login failed.                                        |
| `ERRO: …`  | Technical failure (timeout, unreachable host, etc.). |

## Tuning success detection

Success heuristics live at the top of `core/validator.py` and are easy to customize
per target site:

```python
URLS_SUCESSO    = ["dashboard", "home", "painel", ...]   # URLs indicating success
TEXTOS_SUCESSO  = ["logout", "sair", "minha conta", ...]  # on-page success text
SELETORES_LOGIN = ["input[data-testid='field-login']", ...]
SELETORES_SENHA = ["input[type='password']", ...]
```

## License

[MIT](LICENSE) © 2026 Matheus Trindade
