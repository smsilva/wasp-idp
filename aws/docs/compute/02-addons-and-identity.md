# 02 — Add-ons and Identity

**Pilar WAF principal:** Security (identidade de workload) + Operational Excellence (ordem correta).

## Um cluster cru não faz nada útil sozinho

Control plane + node groups dão um cluster que **agenda pods** — mas sem storage persistente,
sem DNS, sem ingress, sem acesso a segredos. Os **add-ons** preenchem isso, e quase todos
precisam de **identidade AWS** (para criar volumes, escrever DNS, ler segredos). É aqui que
Compute e [`security/04-workload-identity.md`](../security/04-workload-identity.md) (identidade de workload) se encontram.

## Os add-ons desta referência

| Add-on | Faz | Identidade que precisa |
|---|---|---|
| **eks-pod-identity-agent** | habilita Pod Identity no cluster | — (é o que emite identidade aos outros) |
| **aws-ebs-csi-driver** | volumes EBS para PVCs | role com EC2 volume actions |
| **external-dns** | publica DNS por app ([`dns/04-automation-and-tls.md`](../dns/04-automation-and-tls.md)) | role Route53 escopada |
| **aws-load-balancer-controller** | materializa NLB/ALB (tópico 4) | role ELBv2/EC2 escopada por tag |
| **cert-manager** | TLS via DNS-01 ([`dns/04-automation-and-tls.md`](../dns/04-automation-and-tls.md)) | role Route53 da subzona |
| **external-secrets (ESO)** | sincroniza Secrets Manager → K8s Secret | role `secretsmanager:GetSecretValue` escopada `poc-eks/*` |

Cada um roda com uma **ServiceAccount** própria, associada a uma **role própria, escopada** —
menor privilégio por add-on, não uma role gorda compartilhada.

## Pod Identity — a identidade nativa (preferida)

Todos os add-ons acima recebem credencial AWS via **Pod Identity** ([`security/04-workload-identity.md`](../security/04-workload-identity.md)), não
access key montada:

```text
1. Add-on eks-pod-identity-agent instalado no cluster
2. Role <prefix>-<addon>-role com policy escopada + trust em pods.eks.amazonaws.com
3. PodIdentityAssociation: liga ServiceAccount <ns>/<sa>  ↔  a role
4. O pod do add-on assume a role e recebe STS rotacionada (AWS_CONTAINER_CREDENTIALS_FULL_URI)
```

- **Trust fixa `pods.eks.amazonaws.com`** — só o serviço de Pod Identity assume, não um
  principal arbitrário.
- **Policy escopada** por add-on: ESO só lê `poc-eks/*`; LB Controller só muta recursos com a
  tag do cluster; external-dns só a zona filtrada. Um add-on comprometido não alcança o
  território de outro.
- **IRSA** é a alternativa mais antiga (via OIDC provider); Pod Identity é o preferido aqui
  (mais simples, sem gerir OIDC).

## A ordem importa — a race de Pod Identity (gotcha real)

O erro estrutural mais custoso do PoC: aplicar **add-on + role + association + o workload** num
mesmo passo, sem ordem garantida. Se o pod do add-on sobe **antes** da `PodIdentityAssociation`
resolver, ele nasce **sem credencial** → `CrashLoopBackOff` (`no EC2 IMDS role found`) e o
add-on trava em `CREATING` — o que já **matou o provisionamento inteiro** (o `wait` estoura sob
`set -e`).

```text
Errado:  association + workload no mesmo apply  →  pod sobe sem credencial  →  CrashLoop ❌
Certo:   1) aplicar association  →  esperar Ready
         2) SÓ ENTÃO aplicar o workload (add-on/Release)  →  pod nasce já com credencial ✅
```

**Regra (validada no EBS CSI e no ESO):** a identidade (role + association) é uma **fase à
parte**, aplicada e aguardada **antes** do workload que a consome. É por isso que o modelo
faseado separa `65-pod-identity` de `68-ebs-csi-driver`, `80-eso-pod-identity` de
`82-external-secrets`, etc. — a fase da identidade sempre precede a fase do consumo.

## Add-ons gerenciados vs. via Helm

- **Add-ons gerenciados pelo EKS** (EBS CSI, Pod Identity agent) — instalados como
  `Addon`/`ClusterAddon`, a AWS cuida da versão compatível.
- **Add-ons via Helm** (external-dns, LB Controller, cert-manager, ESO, Istio) — instalados
  como `Release` (`provider-helm`), versão de chart pinada. Cada um com sua fase de identidade
  antes.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC02-BP02 — Use temporary credentials](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html)** | Pod Identity emite STS rotacionada; sem access key no pod |
| **[SEC03-BP01 — Define access requirements](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_define.html)** | role escopada por add-on (ESO só `poc-eks/*`, LB só por tag) |
| **[OPS05 — Design for operations](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/design-for-operations.html)** | identidade (role+association) numa fase que **precede** o workload |
| **REL** resiliência de provisionamento | evitar a race elimina o CrashLoop que matava o provision |

## Próximo

→ [`03-access-and-rbac.md`](03-access-and-rbac.md): quem — humano ou automação — tem RBAC dentro do
cluster.
