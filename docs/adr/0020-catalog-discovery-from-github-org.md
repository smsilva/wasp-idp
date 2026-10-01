# Catalog discovery from the wasp-foundry GitHub org

**Status:** Aceito (2026-10-01)

## Contexto

O Backstage local usa SQLite em memória: tudo registrado por `catalog:register` ou pela UI some quando o backend reinicia. Registrar cada repo como location fixa no `app-config.yaml` resolveria a persistência, mas exigiria um commit no `wasp-idp` para cada aplicação nova da org.

## Decisão

**O catalog descobre os repos da org `wasp-foundry` pelo entity provider do GitHub** (`@backstage/plugin-catalog-backend-module-github`, `catalog.providers.github.waspFoundry`): lê `/catalog-info.yaml` da `main` de cada repo a cada 5 minutos, autenticado pelo App `wasp-foundry-backstage`. Entidades da plataforma que não pertencem a um repo (Domain, System, Resources dos clusters, times) ficam em `idp/catalog/` como locations de arquivo.

## Consequências

- Reiniciar o backend não perde aplicações: o primeiro ciclo do provider (15 s após o start) reconstrói o catalog.
- Aplicação nova aparece sem passo extra; o `catalog:register` do template continua só para o registro imediato, e o catalog mantém uma entidade só.
- A descrição de cada serviço vive no próprio repo (`catalog-info.yaml`, `openapi.yaml`) e muda no mesmo PR que o código.
- Um repo da org com `catalog-info.yaml` inválido gera erro de processamento visível só no log do backend.
