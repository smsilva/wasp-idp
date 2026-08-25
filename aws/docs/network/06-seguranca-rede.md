# 06 — Segurança de Rede

**Pilar WAF principal:** Security ([SEC05 — Protecting networks](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-networks.html); [SEC06 — Protecting compute](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-compute.html);
[SEC04 — Detection](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/detection.html)).

## Camadas de defesa (defense in depth)

O isolamento por conta + route table (tópico 3) controla **roteamento**. Ele não basta
sozinho: tráfego pode chegar por caminhos não previstos. Empilhe camadas:

```text
1. Conta (blast radius)          ← tópico 3
2. TGW route table por spoke     ← tópico 3  (o que um spoke pode ROTEAR)
3. Security Group (stateful)     ← este tópico (o que um recurso ACEITA)
4. NACL (stateless, por subnet)  ← este tópico (guarda grossa por subnet)
5. VPC Flow Logs (detecção)      ← este tópico (o que de fato TRAFEGOU)
```

## Security Groups (stateful — a camada primária)

- **Stateful**: resposta de conexão permitida é automática; você declara só a direção inicial.
- **Regras base recomendadas** (ajustar por workload):
  - **Privado**: permitir tráfego intra-VPC (do próprio CIDR); permitir portas de app
    (ex.: 443); egress liberado para pull de imagens/APIs via NAT.
  - **Público**: permitir 80/443 de onde o ingress vem (internet ou APIM/Front Door);
    egress controlado.
- **Referência por SG, não por CIDR**, quando possível — `sg-app` permite de `sg-lb` em vez
  de um range de IP. Mais preciso e resiliente a mudança de CIDR.
- **Cross-cloud/on-prem**: permitir explicitamente o CIDR do Hub / do peer VPN, não
  `0.0.0.0/0`.

## NACLs (stateless — guarda grossa por subnet)

- **Stateless**: precisa de regra de ida **e** de volta (portas efêmeras).
- Use como rede de segurança grossa por subnet (ex.: negar RFC1918 que não seja do Hub/VPC),
  não como controle fino — esse é papel do SG.
- Regra típica de isolamento: **permitir** CIDR da própria VPC + CIDR do Hub; **negar** o
  resto de `10.0.0.0/8` (outros tenants); default allow abaixo.

## VPC Flow Logs (detecção)

- Habilitar Flow Logs na VPC de cada spoke → CloudWatch Logs ou S3.
- É a fonte de verdade de **o que realmente trafegou** — essencial para investigar
  isolamento ("o spoke A tentou alcançar o B?") e para forense.
- **[SEC04-BP01 — Configure service and application logging](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_detect_investigate_events_app_service_logging.html)**: sem Flow Logs, uma violação de isolamento é invisível até alguém reclamar.

## VPC Endpoints (reduzir superfície e custo)

- **Gateway endpoints** (S3, DynamoDB): tráfego para esses serviços não sai pela internet
  nem pelo NAT — fica dentro da AWS. Grátis. Associados às route tables privadas.
- **Interface endpoints** (ECR, STS, Secrets Manager, etc.): acesso privado a APIs AWS sem
  NAT; reduz superfície e dependência de saída pública. Têm custo por hora + por GB.
- Benefício duplo: **segurança** (não passa por NAT/internet) + **custo** (menos tráfego NAT).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC05-BP01 — Create network layers](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_create_layers.html)** | conta → TGW RT → SG → NACL |
| **[SEC05-BP02 — Control traffic flow within your network layers](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_layered.html)** | SG stateful + NACL stateless + rotas |
| **[SEC05-BP03 — Implement inspection-based protection](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_inspection.html)** | Gateway/Interface endpoints evitam exposição pública |
| **[SEC04-BP01 — Configure service and application logging](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_detect_investigate_events_app_service_logging.html)** | VPC Flow Logs em todos os spokes |
| **COST** | Gateway endpoints reduzem tráfego NAT (cobrado por GB) |

## Próximo

→ [`07-mapa-crossplane.md`](07-mapa-crossplane.md): como tudo isso vira XRD/Composition, o
que já roda no PoC e o gap até o alvo.
