# Play Validator — Auditoria de Credenciais

Ferramenta para validação automatizada de credenciais via browser, com geração de relatório para auditoria.

## Estrutura

```
play-validator/
├── main.py                  # Ponto de entrada
├── requirements.txt
├── core/
│   ├── reader.py            # Leitura e normalização do CSV
│   └── validator.py         # Pool de validação assíncrona (Playwright)
├── reports/
│   └── generator.py         # Geração de relatório CSV + TXT
└── input/
    └── exemplo.csv          # Modelo de CSV de entrada
```

## Instalação

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Instalar o browser (apenas uma vez)
playwright install chromium
```

## Formato do CSV de entrada

```
login;password;url;login_type
usuario@empresa.com;senha123;https://sistema.empresa.com;
11122233344;pass456;https://portal.cliente.com;cpf
```

Colunas aceitas:
- **login** — também aceita: `username`, `email`, `user`
- **password** — também aceita: `senha`, `pass`
- **url** — também aceita: `host`, `site`
- **login_type** — opcional. Use `cpf` para extrair apenas dígitos do login

## Uso

```bash
# Básico
python main.py input/credenciais.csv

# Com saída personalizada e 20 workers
python main.py input/credenciais.csv relatorio.csv --workers 20

# Com timeout maior (redes lentas)
python main.py input/credenciais.csv --timeout 60
```

## Saída

Dois arquivos são gerados:
- `relatorio_auditoria.csv` — todos os resultados com timestamp, host, login, senha e status
- `relatorio_auditoria.txt` — resumo legível para auditoria, com credenciais válidas destacadas

## Status possíveis

| Status    | Descrição                                        |
|-----------|--------------------------------------------------|
| VÁLIDO    | Login bem-sucedido (URL ou texto de sucesso)     |
| INVÁLIDO  | Login falhou                                     |
| ERRO: ... | Falha técnica (timeout, host inacessível, etc.)  |

## Ajustar detecção de sucesso

Edite `core/validator.py`:

```python
# URLs que indicam sucesso
URLS_SUCESSO = ["dashboard", "home", "painel", ...]

# Textos na página que indicam sucesso
TEXTOS_SUCESSO = ["logout", "sair", "minha conta", ...]

# Seletores dos campos (em ordem de prioridade)
SELETORES_LOGIN = ["input[data-testid='field-login']", ...]
SELETORES_SENHA = ["input[type='password']", ...]
```

## Infos adicionais

[core/reader.py] — se o CSV vier em formato diferente, edita aqui
[core/validator.py] — seletores dos campos de login/senha e palavras-chave de sucesso ficam no topo do arquivo, fácil de customizar por site
[reports/generator.py] — gera CSV completo + TXT legível para auditoria