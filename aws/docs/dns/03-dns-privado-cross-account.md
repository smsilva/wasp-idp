# 03 — DNS Privado e Cross-Account

**Pilar WAF principal:** Security (nomes internos não vazam para a internet; resolução controlada).

## Quando o público não serve

Nomes internos — um banco, um serviço só-VPC, um host corporativo on-prem — **não devem** ter
record público (expõe topologia e superfície). A resposta é a **Private Hosted Zone (PHZ)**:
uma zona que resolve **apenas** dentro das VPCs a ela associadas, invisível na internet.

```text
Público  (tópicos 0-2)   app.blue.aws.example.com   →  internet resolve  →  NLB
Privado  (este tópico)   db.blue.internal           →  só a VPC associada resolve  →  IP interno
```

Uma PHZ pode até usar o **mesmo nome** de uma zona pública, com respostas diferentes por
origem (*split-horizon* — tópico 0): dentro da VPC resolve ao IP privado, fora resolve ao
público (ou nem resolve).

## Private Hosted Zone — o básico

- Criar a PHZ para o domínio interno (`<spoke>.internal` ou o corporativo).
- **Associar à VPC** do spoke — só VPCs associadas resolvem aquele domínio.
- Records normais (A, CNAME, SRV) dentro dela, sem delegação pública (não há record NS na
  raiz pública — a PHZ é autoritativa só para quem a enxerga).

## Route53 Resolver — quando a resolução cruza fronteiras

A PHZ resolve o que está **nela**. Para encaminhar queries **entre** ambientes (VPC ↔ on-prem,
VPC ↔ outro resolver), entram os **Resolver endpoints**:

| Endpoint | Direção | Uso |
|---|---|---|
| **Inbound** | de fora → para a VPC | on-prem resolve nomes da sua PHZ |
| **Outbound** | da VPC → para fora | a VPC encaminha domínios corporativos a um resolver externo (on-prem via VPN) |

- **Regras de forwarding** dizem *qual domínio* vai para *qual resolver* (ex.:
  `corp.example.com` → resolver on-prem via o outbound endpoint).
- Exigência AWS: endpoints de Resolver precisam de IPs em **≥2 subnets em AZs distintas**
  (HA) — reservar isso no plano de subnets (`../network/02`).
- O tráfego DNS on-prem fecha pela **VPN no Hub** (`../network/04`) — coerente com "tudo
  externo passa pelo Hub".

## Resolução cross-account — uma PHZ para várias contas

Num multi-account, um serviço central (ex.: no Hub) pode precisar resolver nomes de PHZs que
vivem em contas de projeto, ou vice-versa. O mecanismo é a **associação de VPC cross-account**:

```text
Conta A (dona da PHZ)                     Conta B (VPC que quer resolver)
  CreateVPCAssociationAuthorization  ──►  (autoriza a VPC de B)
                                     ◄──  AssociateVPCWithHostedZone (B associa sua VPC)
```

Dois passos, duas contas: a **dona autoriza** (`VPCAssociationAuthorization`), a **outra
associa**. Sem a autorização, a associação cross-account é negada — é o controle de segurança
que impede associar uma VPC arbitrária a uma PHZ alheia. No mundo Crossplane, os dois MRs
(authorization + association) são materializáveis, coerente com as roles cross-account de
`../security/02`.

## Ordem de precedência (split-horizon na prática)

Dentro de uma VPC com PHZ associada, para um domínio que existe nas duas árvores:

```text
1. PHZ associada à VPC        ← vence, se o nome casa
2. Resolver rules (forward)   ← se não casou na PHZ
3. Público (internet)         ← fallback
```

É por isso que um host dentro da VPC pode ver um IP privado enquanto o mundo vê o público — e
por que um erro de associação de PHZ faz "resolve diferente dependendo de onde eu rodo".

## Nesta PoC

O caso central do PoC é **público** (expor apps do cluster). DNS privado/Resolver
cross-account é **alvo mapeado**, não estado atual — entra quando houver resolução interna
on-prem/cross-account de fato. Documentar aqui é o mapa.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC05-BP01](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_create_layers.html)** não expor o que é interno | PHZ resolve só dentro da VPC; sem record público |
| **[SEC03-BP07](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_analyze_cross_account.html)** acesso cross-account controlado | `VPCAssociationAuthorization` exige autorização explícita da dona |
| **[REL02-BP01](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_users.html)** resolução HA | Resolver endpoints em ≥2 AZs; forwarding via VPN no Hub |

## Próximo

→ [`04-automacao-e-tls.md`](04-automacao-e-tls.md): external-dns e cert-manager — quem escreve
os records e emite os certificados.
