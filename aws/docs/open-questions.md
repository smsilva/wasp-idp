# Open Questions / Hypotheses

Perguntas em aberto sem decisão tomada. Quando uma pergunta vira decisão, sai daqui e vira ADR em
[`docs/adr/`](../../docs/adr/); quando vira trabalho concreto, vira issue no GitHub e só a
referência fica aqui.

- **Teto de 25 certificados por ALB** (excluindo o default) e 100 rules, ambos ajustáveis por
  Service Quotas. O certificado aperta primeiro ⟹ 25 clientes/células por ALB (ver
  [ADR 0010](../../docs/adr/0010-one-acm-wildcard-per-cluster.md)). Mesma família do teto de CIDR
  ([ADR 0003](../../docs/adr/0003-supernet-cidr-allocation.md)): saber antes de prometer escala.
- **Session tags em `assumeRoleChain`:** a contenção regional por `aws:RequestedRegion` =
  `aws:PrincipalTag/region` depende de o provider-aws propagar tags de sessão. **Não verificado.**
  Se não propagar, a condição nunca casa e tudo é negado.
- **O cluster deveria receber só as subnets PRIVADAS, em vez de as quatro?** O
  `control_plane_subnet_ids` de `src/network` entrega públicas + privadas, espelhando o desenho de
  referência do Crossplane — desenho de quando o endpoint era público. Com o endpoint privado, ENI
  de control plane em subnet pública não serve a nada (foi ela que causou o incidente registrado em
  `known-broken.md`). Resolvido por rota (aditivo, não recria o cluster); estreitar para privadas
  seria mais correto conceitualmente, mas muda a semântica de um output de módulo compartilhado e
  pode forçar replace do `aws_eks_cluster`. **Não decidido** — decidir antes de a próxima célula
  nascer, não depois.
- **Fase 3 (ingress) não foi revisitada à luz do SNAT do Client VPN.** O caminho ALB→NLB→gateway
  não passa pelo Client VPN, então provavelmente não muda nada — mas o
  `X-Forwarded-For`/`numTrustedProxies` já era ponto de atenção ali, e vale conferir junto com a
  issue #9 (provas negativas de isolamento).
- **Quantas subnets privadas do hub associar por AZ, e o custo de cada associação.** A AWS cobra
  por associação de target network no Client VPN — associar as duas subnets privadas dobra essa
  parcela em troca de redundância de AZ. O plano assume duas; se o custo apertar, uma resolve para
  PoC.
- **Domínio pessoal em arquivo versionado:** `01-preparation.md:88` cita o domínio real por
  extenso, vindo do desenho original. Não está na lista de tokens proibidos (que é sobre a trilha
  corporativa), mas é identidade num repo público. **Não mexido de propósito** — é decisão de quem
  escreveu.
- **Rework do orquestrador `environment/`** (BLOCKED): sob `metadata.name`, filhos compostos
  ganham nome hasheado → o cruzamento por label compartilhado não funciona. Conserto desenhado em
  `resources/examples/topology/05-07`. Adiado. `aws/docs/compute/06-crossplane-map.md` registra o
  alvo: **remover `Environment`; `Cluster` é o topo**.
- **Conta `security-tooling`** desenhada como slot, não criada — vira pré-requisito quando
  GuardDuty/Config/Security Hub entrarem.
- **Contas `Monitoring` / `Operations Tooling`** (OU `Infrastructure`) são os slots canônicos da
  observabilidade centralizada; nenhuma existe.
- **Trilha Azure pausada ganhou destino:** `azure/terraform/simulated-client/` cria o slot
  `azure/terraform/`, onde `cluster-zero` pode aterrar depois.
- **Cluster naming idea (not decided):** OpenStack's TripleO project uses `Undercloud` (the
  bootstrap/control cluster that deploys and manages) and `Overcloud` (the workload cluster it
  produces) — possible naming inspiration for cluster-zero (undercloud-like) vs. per-project
  Backstage clusters (overcloud-like).
- ~~`src/hub` e `src/cell` escolhem AZ por `data.aws_availability_zones` independentes~~ —
  **corrigido** (revisão final da fase 3). A leitura original ("as duas chamadas batem na mesma
  API, mesma conta/região") estava **errada**: `module.hub` aplica com `providers = { aws =
  aws.network }` (conta `network`) e `module.cell` aplica com o provider default (conta `cicd`).
  Um `data.aws_availability_zones` sem provider explícito sempre resolve no provider default da
  raiz que o declara — o antigo data source interno de `src/cell` rodava sempre em `cicd`, e o
  antigo data source único da raiz também, mesmo alimentando `module.hub` que aplica em
  `network`. AZ names são alias por-conta sobre AZ IDs físicos: as duas contas podem enxergar
  `us-east-1a` como zonas físicas diferentes. Fix: dois `data.aws_availability_zones` na raiz
  (`regions/<r>/main.tf`), um com `provider = aws.network` alimentando `module.hub`, outro sem
  provider (conta `cicd`) alimentando `module.cell` via a variável nova `var.availability_zones`
  — `src/cell` não tem mais data source próprio.
