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

## Invariante

**Um hub regional com o seu control plane tem que poder ser criado em outra região.** Não "depois",
não "com um passo manual a mais": a segunda região é a razão de a raiz ser por região. Este
invariante está acima de qualquer conveniência das fases.

O que ele implica, concretamente:

- **Nenhum artefato de uma região mora dentro do diretório de outra.** Se `regions/us-west-2/`
  precisa de um arquivo, ele vive em `variables/` (compartilhado) ou em `regions/us-west-2/` — nunca
  num symlink apontando para `regions/us-east-1/`.
- **Todo nome de namespace global carrega a região.** IAM (roles, SAML providers) e Route 53 (a
  subzona é uma só para a Organization inteira) não são regionais. Dois nomes iguais em duas regiões
  colidem — em IAM com `EntityAlreadyExists`, em Route 53 sobrescrevendo em silêncio, que é pior. A
  regra já existia para `crossplane-cp-<região>` em
  [`08-control-plane-identity.md`](../../../../aws/docs/security/08-control-plane-identity.md); aqui
  ela vira geral.
- **Nenhum script pergunta em qual região está** — recebe `--region` ou itera `regions/*`. Script com
  região escrita no corpo é violação, não detalhe.
- **A diferença entre a primeira e a segunda região é operacional, não estrutural.** Aplicar só o hub
  numa região é decisão de custo. `terraform plan` da composição inteira — hub **e** célula — tem que
  ser verde nas duas.

**Como usar isto durante a execução:** se um passo de fase, um script ou uma verificação só funciona
porque a região é `us-east-1`, o passo está errado — não é para contorná-lo, é para parar e
reponderar. Cada fase tem uma linha de aceite marcada **(invariante)** que existe só para isso.

## Os dois eixos: ordem e permanência

Foram confundidos uma vez e vale fixar, porque a confusão produziu um "T-1" que não existe.

- **Ordem** é o prefixo numérico dos scripts: `00`, `01`, `02`. Diz o que roda antes do quê.
- **Permanência** é `T0`/`T1`/`T2`, definida em
  [`2026-08-26-private-access-and-ingress`](../2026-08-26-private-access-and-ingress/README.md) por
  custo e ciclo de vida: T0 permanente e ~zero custo, T1 de pé durante o dia e destruído à noite, T2
  sobe/valida/desce.

São eixos independentes. Não existe nível "antes do T0": a fundação da Organization é a coisa **mais**
permanente do repositório — T0, como o bucket de state.

| Ordem | Camada | Permanência | Terraform? |
|---|---|---|---|
| — | Organization, contas, OUs, SCP, Identity Center | T0 | não — `aws/docs/accounts/scripts/` |
| 00 | `state-backend/` | T0 | sim |
| 01 | `dns/` | T0 | sim |
| 02 | `regions/<r>` → `module.hub` | **T1** | sim |
| — | conectar o túnel do Client VPN | — | não |
| 02 | `regions/<r>` → `module.cell` | **T2** | sim |
| — | providers e Compositions do Crossplane | T2 | não — GitOps |

Duas consequências que a fase 4 tem que escrever no `aws/terraform/README.md`:

1. **`module.hub` e `module.cell` dividem o número `02` e têm permanências diferentes.** É a novidade
   desta frente. `platform-status` reporta custo *por raiz* hoje; com os dois níveis na mesma raiz,
   ele passaria a somar T1 e T2 numa linha só — tem que passar a reportar por módulo.
2. **A fundação não ganha um `up-00`.** O prefixo `up-NN` significa "raiz Terraform, idempotente,
   roda sozinha", e a fundação não é nenhuma das três: roda uma vez na vida, `create-account` exige
   e-mail de root único e não é re-executável, e o app SAML é console. Ela aparece na tabela de
   sequência como bloco próprio acima do `up-*`, com a ordem que os documentos `00-strategy` …
   `07-cloudtrail` de `aws/docs/accounts/` já estabelecem.

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
- **Nada de região escrita no corpo de script ou de módulo.** `src/hub` e `src/cell` recebem a região
  por variável; os scripts recebem por `--region`. A única região literal legítima está no `locals`
  de uma raiz `regions/<r>/` — que é onde ela *deve* estar, uma vez, por região.

## Fases

Um arquivo por fase — ler só a do trabalho corrente.

| Fase | Arquivo | Entrega | Aceite |
|---|---|---|---|
| 1 | [`01-single-tfvars.md`](01-single-tfvars.md) | `variables/values.tfvars` único; `generate-tfvars` removidos; valores estruturais viram default/inline | `terraform plan` verde nas três raízes atuais, sem passo de geração — **sem apply** |
| 2 | [`02-hub-module.md`](02-hub-module.md) | `src/hub` (ex 01+03) e a raiz `regions/us-east-1/` com só `module.hub` | hub de pé aplicado da raiz nova; túnel do Client VPN conecta |
| 3 | [`03-cell-module.md`](03-cell-module.md) | `src/cell` (ex 04) ligado por output do hub; nenhum data source cross-camada | `curl` público em `cell_services_url` devolve 200; `destroy -target=module.cell` preserva o hub |
| 4 | [`04-cleanup-and-docs.md`](04-cleanup-and-docs.md) | raízes antigas e state keys apagadas, `regions/us-west-2/`, docs e scripts `up-*` renumerados | **`plan` verde da composição inteira na `us-west-2`**; árvore limpa aplica do zero seguindo só o `README.md` |
| 5 | [`05-spoke-enablement.md`](05-spoke-enablement.md) | a role `crossplane-<alvo>` nas contas-alvo; `docs/bootstrap/` reescrito para Pod Identity | um Composition cria recurso real numa conta-alvo e fica `READY=True` |

**A fase 1 entrega o critério de aceite da issue #36 sozinha.** Era para ser aplicável na AWS
isoladamente — o walk skeleton desta frente —, mas em 2026-08-30 se decidiu **pular o apply da 03
nela**: a fase 2 destrói 01 e 03 poucas horas depois, e o apply real acontece uma vez só, da raiz
regional. O aceite da fase 1 passa a ser `plan` puro nas três raízes, que exercita todas as variáveis
do `values.tfvars` — incluindo `base_domain`, onde a #36 nasceu. As fases 2 e 3 não têm valor parcial: o aceite
da frente é a célula ponta a ponta.

**A fase 5 é independente das outras quatro** e pode correr em paralelo à 2 e à 3: ela não toca em
`regions/`, `src/hub` nem `src/cell` — consome delas só o *nome* da role de Pod Identity da célula.
Ela existe porque as fases 1-4 entregam o control plane com o Crossplane instalado e **o outro lado do
assume role não existe**: hoje `aws/eks/providers/spoke-trust-policy.json` confia no IAM user da era
k3d, e nenhum script o aplica. Sem a fase 5, o primeiro Composition morre com `AccessDenied`.

**A fase 4 é onde o invariante é cobrado, mas não é onde ele é construído.** A `us-west-2` só planeja
limpa se as fases 2 e 3 já tiverem parametrizado a região e regionalizado os nomes globais. Descobrir
isso na fase 4 significa reabrir as fases 2 e 3 — por isso cada uma delas tem a sua própria linha de
aceite **(invariante)**, verificável sem uma segunda região existir.

## Estrutura final de arquivos

```
aws/terraform/
  variables/
    values.tfvars.example        VERSIONADO — o inventário, com placeholders
    values.tfvars                GITIGNORED — os valores reais desta conta
    saml-metadata.xml            GITIGNORED — uma aplicação do Identity Center, todas as regiões
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
    us-west-2/                   idem — mesma composição, mesmos módulos; só os locals mudam
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
| `saml_metadata_path` | checado pelo script, arquivo dentro de `connectivity/us-east-1/` | **`variables/saml-metadata.xml`** gitignored, symlinkado por cada raiz regional — o ACS URL do Client VPN é `http://127.0.0.1:35001` para qualquer endpoint, então **uma** aplicação do Identity Center serve todas as regiões. Manter o arquivo na pasta de uma região violaria o invariante (e a fase 4 apaga essa pasta) |
| `name` da célula (`"control-plane"`) e do hub (`"poc-hub"`) | literal sem região | **carregam a região** — nomeiam role de IAM e record do Route 53, os dois namespaces globais |
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
| **IAM e Route 53 são globais; a segunda região colide** — `poc-hub-client-vpn` (SAML provider), `control-plane-crossplane` e as outras quatro Pod Identity roles, `vpn.<subzona>`, `*.control-plane.<subzona>` | fases 2 (hub) e 3 (célula); **explode só na fase 4**, longe da causa | região no nome, e um teste por módulo que assere o nome derivado da região — não o nome literal |
| **`terraform plan` de uma segunda região precisa de credencial e de state próprio** — não dá para provar o invariante offline com `plan` | fase 4 | o aceite offline é o teste de duas execuções (a mesma asserção com duas regiões diferentes), que já é o padrão das fases 1 e 3; o `plan` real da `us-west-2` é o aceite online |

## Fora do plano, de propósito

- **`module.cell` com `for_each`.** Uma célula só, bloco singular. A segunda célula paga o custo de
  generalizar, com `moved` cobrindo a transição (ADR 0014).
- **Migração de state por `moved`/`import`.** `connectivity/` e `control-plane/` estão com zero
  recursos; a `network-foundation/` é recriável em minutos e não guarda dado. O corte é limpo.
- **Rodar o apply de dentro da rede** (CodeBuild em VPC). Continua sendo o destino natural da conta
  `cicd`, e continua sendo outra frente.
- **Modelar o spoke de workload em si** (Composition que cria conta, VPC e attachment). A fase 5 abre
  o caminho — a role de destino — e registra em `open-questions.md` a pergunta que falta: quem aceita
  o attachment do TGW do lado da conta `network`. O spoke em si é outra frente.
- **Trocar o formato do `values.tfvars` por YAML.** O ADR 0013 previa `values.yaml`; o ADR 0014
  escolhe tfvars porque o Terraform o lê direto, sem passo de conversão — que é o passo que esta
  frente inteira existe para eliminar.
