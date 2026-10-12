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
- **O que deve virar efêmero no hub, para o Client VPN parar de custar ~US$ 146/mês parado?** Sem decisão.
  Três opções levantadas, com o trade-off apurado; **não rederivar**:

  | Opção | Custo parado | `.ovpn` entre sessões | Ressalva |
  |---|---|---|---|
  | Só as 2 `aws_ec2_client_vpn_network_association` (+ as 2 rotas) | ~US$ 55 | **estável** — o `dns_name` do endpoint não muda | endpoint, certificado ACM, SAML provider e authorization rules sobrevivem |
  | O Client VPN inteiro | ~US$ 55 | reexportar sempre | certificado revalida por DNS a cada subida |
  | O hub inteiro | US$ 0 | reexportar sempre | inverte a premissa do [ADR 0014](../../docs/adr/0014-single-regional-root-composing-hub-and-cell-modules.md) de que o hub é o resting state |

  A opção cirúrgica existe porque **a cobrança é por associação, não por endpoint**. Ela também
  derruba a nota de [`aws/terraform/CLAUDE.md`](../terraform/CLAUDE.md) de que "o `.ovpn` nunca se reaproveita entre applies do
  hub" — isso vale quando o endpoint é recriado, não quando só as associações vão e voltam.
  **Armadilha já documentada, não tentar:** `transit_gateway_configuration` no endpoint parece o
  caminho mais direto e não é — o attachment que ele cria leva *"several hours"* para deletar, o
  provider não espera, e isso **impede deletar o TGW**.
- **Um retry de teardown é suficiente, ou o caminho é `state rm` automático?** O retry de #94 cobre
  erro transitório. Não cobre finalizer preso por controller sem credencial — nesse caso a segunda
  tentativa falha igual. Com a aresta de #92 o cenário deixa de acontecer por essa causa, mas a
  pergunta continua de pé para outras.
- **Vale abrir exceção na SCP baseline para limpar as VPCs default das 15 regiões negadas?**
  Continua em aberto, mas **deixou de ser o único caminho**: a issue **#69** propõe neutralizá-las com
  *declarative policy* de EC2 (VPC Block Public Access), sem tocar na SCP. O item bloqueante lá é
  medir se a policy dá para restringir por região — aplicada larga, ela mata o ALB público da célula.
- **#40** segue investigação em aberto, sem trabalho iniciado — ver o corpo da issue para os
  ângulos já mapeados.
- **A `gp2` in-tree (`kubernetes.io/aws-ebs`) ainda provisiona volume em Kubernetes 1.36, via CSI
  migration?** Muda se a #62 é gap de qualidade (classe legada, `gp2` mais caro por IOPS que `gp3`)
  ou bug latente (classe que não funciona mais). Conferir na doc da AWS **antes** de escrever
  código — a regra existe porque o passo `2.4` custou ~US$ 180/mês por não fazer isso.
- **Um cluster recém-criado não tem admin além da role de CI**, cuja trust OIDC é restrita a
  `refs/heads/main`. `aws eks update-kubeconfig` + `kubectl` falham com "the server has asked for the
  client to provide credentials". Para depurar de dentro, ou resolver a #56, ou criar uma access
  entry fora do Terraform (`aws eks create-access-entry` + `associate-access-policy`; não gera drift
  porque `var.access_entries` está vazio, então o `for_each` não gerencia nada).
- **Como rotear o tráfego que entra num `Environment` de fora dele?** A rota de workload (#344, [ADR 0035](../../docs/adr/0035-istio-sidecar-per-environment-vcluster-gamma-routes.md)) é east-west: um `HTTPRoute` GAMMA vale só para chamadas feitas de dentro do namespace `apps` do vcluster. Quando houver entrada externa, o gateway de entrada precisa injetar ou validar o header (`x-sandbox`) ou o baggage, e decidir quem pode pedir um sandbox; sem isso, qualquer cliente externo escolheria a instância.
