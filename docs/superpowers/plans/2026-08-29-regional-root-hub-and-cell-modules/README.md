# Regional root composing hub and cell modules

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** substituir as camadas 01/03/04 por uma raiz por região, `aws/terraform/regions/<região>/`,
que compõe `module.hub` e `module.cell` ligados por output, alimentada por um único
`variables/values.tfvars` gitignored — sem nenhum script de descoberta no caminho.

**Architecture:** o acoplamento entre camadas deixa de ser redescoberta (data source por tag/nome +
`generate-tfvars` consultando a AWS CLI) e passa a ser referência dentro de um grafo só.
`state-backend/` (00) e `dns/` (02) continuam raízes próprias; o que era 01+03 vira `src/hub` e o que
era 04 vira `src/cell`. A célula continua descartável por `terraform destroy -target=module.cell`.

**Tech Stack:** Terraform ≥ 1.9, provider `aws` ~> 6.x, `helm` 3.x, `kubernetes` 3.x; `terraform test`
com `mock_provider` para a regressão offline; bash para os scripts `up-*`.

**Spec:** [ADR 0014](../../../adr/0014-single-regional-root-composing-hub-and-cell-modules.md) — a
decisão, os rejeitados e as consequências aceitas. Ler antes de executar qualquer fase.

## Global Constraints

- **`docs/adr/` é imutável depois de aceito.** Divergência entre plano e ADR 0014 vira ADR novo, não
  edição do 0014.
- **Regressão offline verde em toda fase**, antes de qualquer commit que feche um passo:
  `terraform init -backend=false && terraform test` em cada módulo e raiz tocada. Rodar em background
  ou por diretório (a suíte completa passa de 2 min) e sempre com `-no-color`.
- **Nenhum valor por-conta em arquivo versionado.** Domínio, account id, UUID de grupo e ARN real só
  em `variables/values.tfvars` (gitignored) ou `CLAUDE.local.md`. O repositório é público.
- **`terraform apply`/`destroy` nunca síncrono e nunca com `timeout`** — sempre pelos scripts `up-*`
  ou `nohup <comando> > "<log>" 2>&1 < /dev/null & disown`, com o caminho absoluto do log anunciado
  assim que dispara.
- **Scripts em inglês** (comentários, `show_usage`, mensagens); documentação `.md` em pt-BR, títulos e
  nomes de arquivo em inglês.
- **Um `README.md` verdadeiro é entrega, não follow-up.** `aws/terraform/README.md` é a sequência que
  alguém sem contexto copia; atualizá-lo faz parte da fase que muda a sequência.
- **Commits Conventional Commits**, um por passo fechado.

## Fases

Um arquivo por fase — ler só a do trabalho corrente.

| Fase | Arquivo | Entrega | Aceite |
|---|---|---|---|
| 1 | [`01-single-tfvars.md`](01-single-tfvars.md) | `variables/values.tfvars` único; `generate-tfvars` removidos; valores estruturais viram default/inline | `terraform plan` nas raízes atuais sem passo de geração; apply real de 03 |
| 2 | [`02-hub-module.md`](02-hub-module.md) | `src/hub` (ex 01+03) e a raiz `regions/us-east-1/` com só `module.hub` | hub de pé aplicado da raiz nova; túnel do Client VPN conecta |
| 3 | [`03-cell-module.md`](03-cell-module.md) | `src/cell` (ex 04) ligado por output do hub; nenhum data source cross-camada | `curl` público em `cell_services_url` devolve 200; `destroy -target=module.cell` preserva o hub |
| 4 | [`04-cleanup-and-docs.md`](04-cleanup-and-docs.md) | raízes antigas e state keys apagadas, `regions/us-west-2/`, docs e scripts `up-*` renumerados | árvore limpa aplica do zero seguindo só o `README.md` |

**A fase 1 entrega o critério de aceite da issue #36 sozinha** e é aplicável na AWS antes de qualquer
extração de módulo — é o walk skeleton desta frente. As fases 2 e 3 não têm valor parcial: uma raiz
com `module.hub` e sem `module.cell` é o hub sozinho, que é um estado legítimo (é o que a
`us-west-2` será), mas o aceite da frente é a célula ponta a ponta.

## Estrutura final de arquivos

```
aws/terraform/
  variables/
    values.tfvars.example        VERSIONADO — o inventário, com placeholders
    values.tfvars                GITIGNORED — os valores reais desta conta
  state-backend/                 raiz — inalterada (T0, prevent_destroy)
  dns/                           raiz — inalterada (T0, subzona + RAM da Organization)
    values.auto.tfvars           GITIGNORED — symlink para ../variables/values.tfvars
  regions/
    us-east-1/                   RAIZ da região
      main.tf                    module.hub + module.cell + providers
      variables.tf               só identidade; o resto é default ou local
      outputs.tf                 repassa os outputs de aceite dos dois módulos
      versions.tf
      values.auto.tfvars         GITIGNORED — symlink para ../../variables/values.tfvars
      tests/composition.tftest.hcl   a ligação hub -> célula, o único assunto desta raiz
    us-west-2/                   idem, sem module.cell aplicado
  src/
    hub/                         NOVO — VPC hub, TGW, Client VPN, ALB + listener :443
      tests/                     migrados de connectivity/us-east-1/tests/
    cell/                        NOVO — VPC spoke, EKS, NLB interno, charts, lado hub da célula
      tests/                     migrados de control-plane/tests/
    network/ cluster/ nodegroup/ ingress/ pod-identity/ state-backend/ helm/
                                 inalterados — consumidos por src/hub e src/cell
  scripts/
    lib  up-00-state-backend  up-01-dns  up-02-region  up-all  vpn  platform-status
```

Some do disco: `network-foundation/`, `connectivity/`, `control-plane/`, os dois
`scripts/generate-tfvars`, `up-01-network-foundation`, `up-03-connectivity`, `up-04-control-plane`.

## Onde cada valor de hoje vai parar

Esta tabela é a fonte da verdade da fase 1 e o critério para recusar valor novo em `values.tfvars`.

| Valor | Hoje | Depois |
|---|---|---|
| `base_domain` | descoberto da subzona pelos dois scripts | **`values.tfvars`** — identidade, sem default (fail-closed) |
| `subzone_label` | escrito pelos scripts | default `"nonprod"` na variável |
| `operator_group_ids` | Identity Center, nome → UUID | **`values.tfvars`** — UUID é identidade, resolvido à mão uma vez |
| `spoke_account_ids`, `target_account_ids`, `network_account_id` | Organizations, nome → id | **`values.tfvars`** |
| `saml_metadata_path` | checado pelo script | continua variável, default `"saml-metadata.xml"`; o arquivo é passo de console |
| `region`, `aws_profile`, `network_profile`, `hub_vpc_name`, `hub_alb_name`, `client_cidr_block` | opção de script | **default de variável ou `local` na raiz** — decisão de desenho documentada |
| `kubernetes_version` | `describe-cluster-versions` | default de variável, fixado no código e revisado a olho |
| `vpc_cidr` do hub e da célula | inline (hub) / script (célula) | **inline na raiz regional**, como o hub já é ([`01-cidr-addressing.md`](../../../../aws/docs/network/01-cidr-addressing.md)) |
| `availability_zones` | `describe-availability-zones` | **`data.aws_availability_zones`**, hoje não usado |
| `endpoint_public_access` / `public_access_cidrs` | `checkip.amazonaws.com` | variável opcional, ausente por padrão; break-glass declara o CIDR à mão |
| VPC hub, ALB, listener, TGW, route table, attachment | data source por tag/nome na raiz vizinha | **output de `module.hub`** |
| subzona do Route 53 | data source | **continua data source** — pertence à raiz `dns/`, externa |

## Riscos conhecidos e como cada fase os encara

| Risco | Onde morde | Mitigação nesta ordem |
|---|---|---|
| **`mock_provider "helm"` não simula key de release** — colisão de nome passa verde offline e só explode no apply | fase 3, ao mover os módulos de helm para dentro de `src/cell` | asserção explícita de que os nomes de release diferem entre si, no teste de composição |
| **Ordenação é aresta do grafo e `terraform test` não assere grafo** | fases 2 e 3, ao reescrever os `depends_on` que hoje apontam para `module.network` e os seis recursos do TGW | só se dá por boa depois de **um apply E um destroy reais**; a direção se confere lendo quem declara o quê |
| **Acrescentar variável sem default quebra todos os arquivos de teste da raiz** | fase 1, ao tornar `base_domain` obrigatório onde ainda não é | orçar os arquivos irmãos junto, não só o novo |
| **`init -backend=false` numa raiz já inicializada contra o S3 ainda exige credencial** — a linha da regressão sai **vazia**, que se lê como "sem testes" | toda fase | rodar `terraform test` direto nas raízes; nas raízes novas o `init -backend=false` é limpo |
| **`-target` avisa em toda execução que não é para uso rotineiro** | fase 3 em diante | o aviso fica; o script `down-cell` o explica em vez de escondê-lo |
| **Módulo novo herda a constraint de provider da raiz** | fases 2 e 3 | conferir `.terraform/modules/modules.json` depois de acrescentar módulo: módulo ausente ali significa teste da raiz rodando contra árvore velha |

## Fora do plano, de propósito

- **`module.cell` com `for_each`.** Uma célula só, bloco singular. A segunda célula paga o custo de
  generalizar, com `moved` cobrindo a transição (ADR 0014).
- **Migração de state por `moved`/`import`.** `connectivity/` e `control-plane/` estão com zero
  recursos; a `network-foundation/` é recriável em minutos e não guarda dado. O corte é limpo.
- **Rodar o apply de dentro da rede** (CodeBuild em VPC). Continua sendo o destino natural da conta
  `cicd`, e continua sendo outra frente.
- **Trocar o formato do `values.tfvars` por YAML.** O ADR 0013 previa `values.yaml`; o ADR 0014
  escolhe tfvars porque o Terraform o lê direto, sem passo de conversão — que é o passo que esta
  frente inteira existe para eliminar.
