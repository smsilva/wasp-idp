# Documentation navigation structure

**Status:** Aceito (2026-09-01)

## Contexto

251 arquivos `.md` versionados fora de `idp/`, crescidos por acreção, sem estrutura que permita
achar o que se precisa sem contexto prévio — ver #64 para os números completos e o sintoma que
motivou a issue (duplicação de `aws/terraform/ci/README.md` no #52 porque `ci/` não constava da
tabela de Raízes).

## Decisão

Consolidação mínima: os dois troncos físicos existentes (`aws/docs/`, `docs/`) permanecem onde
estão — nenhum `git mv` de conteúdo de referência. Em vez disso:

- Todo `CLAUDE.md` que fazia papel duplo de índice de pasta + regras é dividido: `README.md` vira o
  índice navegável, `CLAUDE.md` fica só com regras imperativas para o agente.
- `README.md` da raiz do repo vira o portão de entrada único, apontando para todos os troncos.
- `docs/superpowers/{specs,plans}/` sai do índice de leitura principal — é memória de processo, não
  referência — sem mover fisicamente.
- Documento cobre um assunto; quando uma seção aprofunda demais um subtema, vira arquivo próprio
  referenciado de onde fazia sentido. Sem limite de linhas fixo.
- `scripts/bin/check-doc-links` verifica link relativo quebrado em todo arquivo versionado (não só
  `*.md`; exclui árvores vendorizadas e `docs/superpowers/`); reutilizável, não é gate de CI nesta
  iteração.

Detalhamento completo:
[`docs/superpowers/specs/2026-09-01-documentation-reorganization-design.md`](../superpowers/specs/2026-09-01-documentation-reorganization-design.md).

## Consequências

- Ganho: qualquer pasta com `CLAUDE.md`+`README.md` tem papel claro; um agente sabe que regra vive
  num arquivo e índice no outro, sem ler os dois para descobrir qual é qual.
- Custo: duas árvores de documentação continuam existindo (`aws/docs/` e `docs/`) em vez de uma só
  — trade-off aceito para manter o risco de link quebrado baixo nesta passada.
- Vazamento de PII conhecido (#23) não foi corrigido por esta decisão — continua rastreado
  separadamente.
- A issue do site MkDocs (próxima) herda uma estrutura decidida, não a bagunça anterior.
