# formae CLI

Exemplo de CLI que expõe as entidades da plataforma (recursos, stacks, targets, políticas) para humanos, pipelines e agentes. Uso: referência para a CLI da plataforma.

## Fontes

- Post indicado pelo usuário: "formae 0.88 is out", blog da Platform Engineering Labs no Medium, <https://blog.platform.engineering/formae-0-88-is-out-e98579c48e73>. **Não lido:** o Medium bloqueia acesso automatizado (Cloudflare 403). O conteúdo abaixo vem da documentação oficial e do release.
- Anúncio do release 0.88 (2026-08-03, PRWeb): <https://www.prweb.com/releases/platform-engineering-labs-advances-human-ai-infrastructure-engineering-with-the-new-formae-release-302840059.html> — "completely redesigned interactive CLI", typed authoring e docs reestruturadas.
- Documentação oficial (lida em 2026-10-07): CLI reference <https://docs.formae.ai/documentation/reference/cli>, `formae inventory` <https://docs.formae.ai/documentation/reference/cli/inventory>, Properties <https://docs.formae.ai/documentation/concepts/properties>, Architecture <https://docs.formae.ai/documentation/concepts/architecture>, AI assistants <https://docs.formae.ai/documentation/guides/ai-coding-assistants>.
- formae é uma ferramenta de IaC open source (licença FSL-1.1-ALv2) da Platform Engineering Labs, escrita em Pkl. É ferramenta de IaC, não portal nem orquestrador: o paralelo aqui é **de design de CLI**.

## O que vale como exemplo

- **CLI e API são o front end da plataforma**: "a consistent interface for people and applications to drive the platform" (Architecture). A CLI só fala com o agente pela REST API; quem executa e guarda estado é o agente. Vários membros do time apontam a CLI para o mesmo agente: uma fonte de verdade.
- **CLI e MCP lado a lado:** o diagrama de arquitetura mostra CLI e MCP como clients irmãos da mesma API. O formae publica um plugin para Claude Code/Codex com MCP tools (inventory, histórico de comandos, schema, simulação, deploy) e skills (simular antes de aplicar, confirmar antes de destruir).
- **Inventário consultável por entidade:** `formae inventory <resources|stacks|targets|policies>`, com filtro `--query` em termos `key:value` e wildcard `*`:

```bash
formae inventory resources --query 'type:AWS::S3::Bucket stack:prod'
formae inventory resources --query 'target:eu target:us managed:false'
formae inventory targets --query 'namespace:AWS label:prod-*'
formae command list --query 'status:InProgress'
```

- **Saída para humano ou máquina:** `--output-consumer <human|machine>` e `--output-schema <json|yaml>`. No terminal, tabela e visão de progresso ao vivo; em pipe/CI, JSON e retorno imediato com ID do comando (acompanhar com `formae command status`).
- **Gerenciados e descobertos:** o inventário inclui recursos que existem na nuvem e ainda não estão sob gestão (`managed:false`); `formae extract` os traz para código. O 0.88 passou a limpar inventário descoberto após um período configurável, sem tocar recursos gerenciados (release).
- **Propriedades tipadas viram flags:** a plataforma esconde o detalhe atrás de uma interface pequena e tipada; o consumidor só passa valores, validados antes de qualquer chamada à nuvem.

```bash
formae apply --help database.pkl     # mostra --team [required], --size [default: "xs"]
formae apply --mode reconcile --team team-a --size s database.pkl
```

- **Simular antes de aplicar:** `apply` em modo humano sempre simula e pede confirmação; `--simulate` para no dry run; `--yes` para automação.
- **Profiles** (`--profile`) trocam de ambiente sem editar config.

## Uso na apresentação

- Slide `many-clients`: a CLI é client de primeira classe, não atalho do portal; CLI e agente (MCP) consomem a mesma API.
- Desenho de uma CLI da plataforma: `inventory` por tipo de entidade do catálogo (Environment, Component, Resource), `--query` por owner/system/lifecycle, saída humana ou JSON, simulação antes de aplicar, flags tipadas derivadas do contrato (como o XRD do `Environment`).
- "Gerenciado vs. descoberto" conversa com ownership e com o ambiente ocioso do Fury (`mercadolibre-fury.md`).
