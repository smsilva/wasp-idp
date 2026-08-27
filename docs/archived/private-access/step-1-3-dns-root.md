# Step 1.3 — DNS Root

_2026-08-26_


Subzona `nonprod.<domínio>` no Route 53 da conta `network` + registro NS de delegação na zona pai no
Azure DNS, numa raiz com dois providers de cloud. **9 runs, 0 falhas. `apply` pendente.**

Quatro desvios do esboço do plano, todos deliberados: `manage_delegation` é **variável** e não
`local` (um `local` não é alcançável por teste, e o propósito — desligar sem editar o resto — se
mantém); valores em `terraform.tfvars` e não inline (única raiz assim: nas outras o inline é decisão
de desenho, aqui é **identidade de quem roda**, e o repo é público); `subzone_label` como variável,
para `prod.` ser outra instância e não exceção; e `azurerm ~> 5.0`, conferido no registry em vez de
herdado do repo Azure pessoal (`~> 4.x`).

**O achado, e vale muito além deste passo: um `override_resource` testa o VALOR, dois testam a
LIGAÇÃO.** `name_servers` só existe depois do apply, então a asserção que prova
delegação-como-código precisa de override. Mas com uma lista fixa no `main.tf` igual aos valores
injetados, a asserção passa sem haver fio — e foi o que aconteceu: a mutação que colava os name
servers à mão passou **verde**. O conserto são dois runs com overrides de valores e tamanhos
diferentes; nenhuma lista fixa satisfaz os dois. Verificado nas duas direções.

**Auditar o repo por asserções com um único `override_resource`** — a de `routing.tftest.hcl` (NAT na
subnet pública) é da mesma família e já usa IDs distintos entre si de propósito, mas não foi checada
sob esta lente.

Regressão: **64 testes em 12 diretórios, 0 falhas** (eram 55).
