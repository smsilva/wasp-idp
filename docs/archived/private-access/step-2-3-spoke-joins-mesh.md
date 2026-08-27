# Step 2.3 — Spoke Joins The Mesh

_2026-08-26_


Aceito com ping real: **3/3 pacotes, 0% de perda, RTT ~140 ms** a um nó do EKS dentro de
`10.2.0.0/16`, pelo túnel. Commits `895e242` (escrita) e `a39430c` (as correções do apply).
Regressão: **104 testes em 13 diretórios, 0 falhas** (eram 86).

**O passo era maior do que o plano dizia — faltava metade.** O texto original descrevia só o lado
da spoke; a exploração achou que **o hub nunca tinha sido anexado ao próprio TGW**. A
`connectivity` criava o TGW e `tgw-rt-hub` e deixava os dois órfãos, sem attachment nenhum — sem
isso o tráfego que chega pelo túnel na subnet privada do hub não tem para onde ir.

**Três achados que nenhuma leitura de tabela de rota daria, todos vindos do apply real:**

- **RAM tem dois portões, não um.** Primeiro `aws_ram_sharing_with_organization` (organization-wide,
  só pela management account) — sem ele, `AssociateResourceShare` é recusado com
  `OperationNotPermittedException`. Ele mora na raiz **`dns/`** (T0, permanente), não em
  `connectivity/` (T1, destruída toda noite): é config da Organization inteira, e um destroy
  noturno não pode desligá-la e religá-la todo dia. Depois, o **aceite do attachment em si** —
  o TGW tem `auto_accept_shared_attachments = disable` de propósito, então o attachment fica em
  `pendingAcceptance` mesmo com RAM resolvido, e associação/propagação/rota falham com
  `IncorrectState`/`InvalidTransitGatewayID.NotFound`, erros que não citam o aceite pendente.
- **O Client VPN faz SNAT.** O tráfego chega à spoke com origem no CIDR da **VPC hub**
  (`10.1.x.x`), não no client CIDR (`100.64.x.x`): liberando só `100.64.0.0/22` no SG do cluster
  o ping não passava; liberando `10.1.0.0/16`, passou. **Duas rotas para o client CIDR chegaram a
  ser escritas** perseguindo a hipótese contrária e foram removidas depois do teste — o retorno
  vai para `10.1.x.x`, já coberto pela rota do supernet. A doc do cenário *"Access a peered VPC"*
  dizia o mesmo por outro caminho: libere o **security group do endpoint** no destino.
  **As tabelas de rota estavam todas certas e mesmo assim não passava** — vale como método:
  hipótese sobre caminho de rede se confere com um pacote, não com leitura de config.
- **Attachment cross-conta tem perpetual diff estrutural** em
  `transit_gateway_default_route_table_{association,propagation}`: write-only, ausentes da API, e
  o provider os deriva das route tables do TGW — que são da conta `network` e invisíveis ao
  provider default (`cicd`). Todo refresh lê `true`, todo plan propõe `true -> false`, para
  sempre. Resolvido com `ignore_changes`, depois de conferir na AWS que o attachment propaga só
  para `tgw-rt-hub`.

**A `authorization rule` por spoke que o plano previa não entrou:** a `2.2` já cobre o supernet
inteiro por grupo. Rota é topologia (cresce aqui, uma vez); authorization rule é política.

**Um `terraform apply` morreu no meio** (o processo caiu; a AWS seguiu provisionando), deixando o
cluster EKS e o NAT criados **fora do state** e um lock órfão. Recuperação: `force-unlock` +
`terraform import` dos dois + plan limpo confirmando zero duplicata. Vale saber que é recuperável
sem destruir nada.

O `connectivity/scripts/destroy` foi corrigido junto: o guard de "attachment de fora" contava o
attachment do **próprio hub** como estranho e teria recusado um destroy legítimo. Agora o exclui
via o output novo `transit_gateway_attachment_id`.

### O teardown, exercitado na mesma sessão — e o que ele provou

Derrubado na ordem inversa: **`control-plane` 46 recursos, `connectivity` 18, 0 falhas nos dois**,
custo por hora de volta a zero (verificado na API: nenhum TGW, endpoint, EKS ou NAT vivo).

- **O guard de precedência foi provado nas três posições**, rodando o `destroy` da connectivity
  fora de ordem de propósito: recusou acusando 2 attachments, recusou acusando 1 depois do fix, e
  passou com 0 depois da control-plane sair. Precedência executável, não parágrafo de README.
- **Armadilha que quase passou batido: fix em script que depende de output novo só funciona
  depois de o output existir no STATE.** O `transit_gateway_attachment_id` tinha sido escrito no
  `outputs.tf` mas nunca aplicado, então `terraform output -raw` devolvia vazio, o guard não
  excluía nada, e a mensagem acusava 2 em vez de 1 — código certo, comportamento errado. Um
  `apply` de **zero recursos** (só materializa o output) resolveu. Vale para qualquer script deste
  repo que leia `terraform output`.
- **O corte de state cross-conta se sustentou no teardown**, que é onde ele seria testado de
  verdade: `tgw-rt-spoke` é recurso da conta `network` mas vive no state do spoke — e **saiu junto
  com o spoke**, sem órfão. É a decisão "fronteira de state segue o ciclo de vida, não a conta"
  funcionando na direção que importa.
- **Tempos, para reconhecer o padrão:** attachment do hub 1m16s, `tgw-rt-hub` 55s, rotas do Client
  VPN ~3m30s cada, **network associations ~7–10 min cada** (simétrico com a criação), registro de
  validação 32s, certificado ACM 1s. O teardown inteiro da connectivity passa de 10 min por causa
  das associations — não é travamento.
- Zero `Service` do tipo LoadBalancer no cluster, conferido **antes** de destruir: o bug do NLB
  órfão (o ticket da trilha corporativa) não tinha como ocorrer aqui. Vale manter a checagem no roteiro.
