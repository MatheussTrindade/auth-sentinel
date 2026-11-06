# Política de Segurança

## Natureza da ferramenta

O **Auth Sentinel** é uma ferramenta de **auditoria defensiva de credenciais**. Ela
automatiza o teste de credenciais expostas (identificadas via threat intelligence,
ex.: Axur) contra os sistemas de login da própria organização, para confirmar quais
credenciais vazadas ainda são válidas e precisam de resposta (troca de senha, bloqueio,
tratamento do incidente).

> ⚠️ **Uso autorizado apenas.** O teste de credenciais contra sistemas ou contas
> para os quais você **não** tem autorização explícita e por escrito pode configurar
> crime (ex.: acesso não autorizado) e violação de leis de proteção de dados.
> Veja a seção "Uso autorizado e responsabilidade" no README.

## Reportando uma vulnerabilidade

Se você encontrar uma vulnerabilidade **neste projeto**, por favor **não** abra uma
issue pública. Em vez disso:

1. Abra um [Security Advisory privado](https://github.com/MatheussTrindade/auth-sentinel/security/advisories/new)
   no GitHub, ou
2. Entre em contato de forma privada com o mantenedor.

Descreva o problema, o impacto e, se possível, um passo a passo para reproduzir.
Faremos o possível para responder em tempo razoável.

## Dados sensíveis

- **Nunca** faça commit de credenciais reais, relatórios (`relatorio*`, `*.csv`,
  `*.txt`), arquivos de entrada (`input/`) ou do arquivo `.env`. O `.gitignore` já
  bloqueia esses padrões — não o contorne com `git add -f`.
- Se um segredo (token da Axur, senha) for exposto em commit, **considere-o
  comprometido** e rotacione-o imediatamente; remover o commit depois não basta.
