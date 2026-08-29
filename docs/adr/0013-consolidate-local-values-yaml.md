# Consolidate local values in a single gitignored YAML; defer formal parameterization

**Status:** Aceito

## Contexto

Valores pessoais/privados (account IDs, e-mails, nomes de recurso, domínio real) não podem entrar
em arquivo versionado — o repositório é público. Hoje esses valores vivem soltos em
`CLAUDE.local.md`, copiados manualmente para onde são necessários (tfvars, chart values). Havia uma
pergunta em aberto sobre qual mecanismo formal deveria injetar esses valores: variável de ambiente,
values file de Helm, ou um `EnvironmentConfig` do Crossplane.

O objetivo atual do repositório é subir **um** ambiente minimamente funcional (hub + spoke control
plane + EKS). A necessidade de um mecanismo formal de parametrização só aparece quando o objetivo
virar **subir N hubs regionais de forma automática** — que é um objetivo futuro, não o atual.

## Decisão

**Adiar** o mecanismo formal de parametrização até a fase de automação multi-hub. Enquanto o
objetivo for um ambiente só, manter os valores em arquivo local é suficiente.

Consolidar os valores hoje espalhados no `CLAUDE.local.md` num único `variables/values.yaml`,
gitignored, em vez de deixá-los soltos misturados com anotações pessoais em prosa.

## Consequências

Nenhuma automação nova é construída agora — só uma organização melhor do que já existe. Quando a
automação multi-hub começar de verdade, este ADR é quem decide que a pergunta "env, values file ou
EnvironmentConfig" fica para aquele momento, com o `values.yaml` como o inventário de partida do que
precisa ser parametrizado.
