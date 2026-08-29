# nonprod subzone delegated to Route 53

**Status:** Aceito

## Contexto

O domínio raiz (apex) já vive no Azure DNS, de fora deste repositório. É preciso decidir onde a
zona usada pelas células AWS (`nonprod.<domínio>`) é servida e gerenciada.

## Decisão

**Subzona `nonprod.` delegada ao Route 53 na conta `network`**, com a delegação **em código** — a
raiz `dns/` roda com providers `aws` + `azurerm` simultaneamente, e é ela quem cria a subzona no
Route 53 e o registro NS correspondente no Azure DNS. O apex continua no Azure.

## Consequências

Uma raiz Terraform com dois providers de cloud tem uma armadilha: sem credencial do segundo
provider, o `plan` falha mesmo para uma mudança que só toca o primeiro. A raiz `dns/` guarda essa
dependência atrás de um `local.manage_*` para não travar plans que não mexem no lado Azure. Qualquer
certificado ACM validado por DNS para células AWS (ADR 0010) depende desta delegação estar correta —
confirmada por `dig +trace` atravessando as duas clouds.
