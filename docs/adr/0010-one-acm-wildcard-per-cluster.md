# One ACM wildcard certificate per cluster

**Status:** Aceito

## Contexto

Cada célula (cluster) expõe um ou mais hosts sob seu próprio subdomínio (ex.:
`services.<id>.nonprod.<domínio>`). É preciso decidir a granularidade de certificado TLS: um
certificado por host, ou um wildcard cobrindo a célula inteira.

## Decisão

**Um wildcard de ACM por cluster**, no formato `*.<id>.nonprod.<domínio>`, com validação por DNS e
renovação automática. Isso encerra a emissão de certificado público por cluster pelo cert-manager,
que passa a cuidar só do certificado interno (mTLS do mesh).

## Consequências

Um wildcard cobre **um nível só** (`*.*.` não existe como padrão de certificado) — daí a
necessidade de um wildcard por cluster em vez de um único wildcard cobrindo `*.nonprod.<domínio>`
inteiro. O teto de 25 certificados por ALB (Service Quota ajustável) vira, na prática, um teto de 25
clientes/células por ALB — ver Open Questions para o detalhamento desse limite.
