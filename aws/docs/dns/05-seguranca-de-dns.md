# 05 — Segurança de DNS

**Pilar WAF principal:** Security ([SEC03](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/permissions-management.html) — permissões escopadas; [SEC04](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/detection.html) — detecção).

## DNS é superfície de ataque e de erro

Numa zona **compartilhada**, quem pode escrever pode sequestrar o nome de outro time
(apontar `app.outrotime` para um IP hostil) ou apagar records por engano. A segurança de DNS
aqui é sobretudo **escopo de escrita** + **detecção** — não há muito segredo, há muito controle
de quem muda o quê.

## IAM do Route53 — a assimetria leitura/escrita

Route53 tem uma limitação que molda a policy: **as actions de leitura não aceitam
resource-level scoping**.

| Action | Escopo por recurso? | Consequência |
|---|---|---|
| `route53:ListHostedZones`, `ListResourceRecordSets`, `ListTagsForResources` | **não** — exigem `Resource: "*"` | leitura é ampla; não dá para restringir por zona na IAM |
| `route53:ChangeResourceRecordSets` | **sim** — `arn:aws:route53:::hostedzone/<id>` | **escrita** pode e deve ser escopada à zona |

Conclusão prática (do PoC): o **isolamento real não vem da IAM de leitura** (que é `*` por
imposição da AWS) — vem de:

1. **`ChangeResourceRecordSets` escopado** ao ARN da(s) zona(s) permitida(s) na inline policy.
2. **`--zone-id-filter` + `--txt-owner-id`** no external-dns (tópico 4) — o controle de posse
   em runtime que a IAM de leitura não consegue dar.

Ou seja: escopar a **escrita** na IAM, e escopar o **comportamento** no external-dns. Depender
só da IAM não isola (a leitura vê tudo); depender só do filtro não basta (sem IAM escopada, um
bug pode escrever fora). As duas camadas juntas.

## Menor privilégio para external-dns e cert-manager

Ambos rodam idealmente com **Pod Identity** (`../security/04`), role escopada:

```text
external-dns role:
  Allow route53:ChangeResourceRecordSets  on  arn:aws:route53:::hostedzone/<subzone-or-parent-id>
  Allow route53:ListHostedZones/ListResourceRecordSets/ListTagsForResources  on  *   (imposto pela AWS)

cert-manager role (DNS-01):
  Allow route53:ChangeResourceRecordSets  on  arn:aws:route53:::hostedzone/<subzone-id>   ← inclui a SUBZONA
  Allow route53:GetChange  on  *
```

O ARN da **subzona** precisa entrar na policy do cert-manager (senão o DNS-01 não escreve o
TXT — o gotcha do issuer por subzona, tópico 4, tem uma contraparte na IAM).

## DNSSEC — integridade da resolução

DNSSEC assina as respostas da zona, provando que não foram forjadas em trânsito (cache
poisoning). Route53 suporta DNSSEC signing por Hosted Zone, com uma KSK em KMS.

- **Trade-off:** habilitar DNSSEC numa cadeia **delegada** exige propagar o registro **DS** na
  zona **pai** — mais um ponto de coordenação com quem gerencia a pai, e mais uma forma de
  quebrar resolução se a chave expira/rotaciona errado.
- **Postura desta referência:** DNSSEC é **alvo opcional**, não baseline — o custo
  operacional (DS na pai, rotação de chave) só se paga onde a integridade de DNS é requisito
  explícito. Documentar como possibilidade, não ligar por reflexo.

## Query logging — detecção

- **Public DNS query logging** → CloudWatch Logs: registra as queries recebidas pela zona
  pública. Útil para ver o que está sendo resolvido (reconhecimento, nomes inesperados).
- **Resolver query logging** (VPC) → o que as VPCs resolvem, alimentando GuardDuty
  (`../security/06`) para detectar exfiltração via DNS.
- Coerente com [SEC04](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/detection.html): sem log de query, um abuso de DNS é invisível.

## Prevenção de sequestro em zona compartilhada

- **Escrita escopada** (IAM + filtro) — a base.
- **`upsert-only`** no external-dns (tópico 4) — evita deleção em massa acidental.
- **Detecção** — query logging + CloudTrail (`route53:ChangeResourceRecordSets` aparece na
  trilha: quem mudou qual record, quando).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC03-BP01](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_define.html)** menor privilégio | escrita escopada ao ARN da zona; leitura `*` só por imposição da AWS, compensada por filtro |
| **[SEC03-BP02](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_least_privileges.html)** controle por atributo | `--txt-owner-id` dá posse por record em zona compartilhada |
| **[SEC04-BP01](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_detect_investigate_events_app_service_logging.html)** capturar eventos | query logging + CloudTrail das mudanças de record |
| **SEC** integridade (opcional) | DNSSEC onde a integridade de resolução é requisito |

## Próximo

→ [`06-mapa-crossplane.md`](06-mapa-crossplane.md): o XR `DnsZone` e como external-dns e
Crossplane dividem a responsabilidade.
