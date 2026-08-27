# Provisioning sequence of the `Environment` — the monolith

> **Historical reference.** This is a portrait of a Crossplane monolith from the corporate trail,
> kept because it is what the 32 files of
> [`2026-08-20-resource-dictionary.md`](2026-08-20-resource-dictionary.md) describe. The
> authoritative sequence for this repository is
> [`2026-08-27-provisioning-sequence.md`](2026-08-27-provisioning-sequence.md), which starts at
> account bootstrap and ends at the spoke.

**Source:** this document describes the monolithic `environment-eks` Composition
(function-kcl, `Environment` / `platform.example.com`) as it stands in the corporate trail.
Creation order, layer by layer, reviewed against the composition. This repo's own
`aws/eks/resources/environment/composition.yaml` is a much smaller, decomposed façade and is
**not** the subject of this document.

**How to read (YAML):** **nesting = primary blocker** (the parent is provisioned first). Comments:
`# needs:` = additional dependency (besides the parent) · `# gate:` = only created once Ready · `# →` =
what it produces. `outputs:` = the contract that the layer publishes for the next ones. Below each
block, the **Definitions** links point to each resource's file (index in the
[resource dictionary](2026-08-20-resource-dictionary.md)).

---

## 01 · network

```yaml
vpc:
  subnets:
    - public-1a
    - public-1b
    - private-1a
    - private-1b
  internet-gateway:

nat-elastic-ip:
  nat-gateway:                 # needs: subnets/public-1a

route-tables:                  # needs: vpc
  public:
    route-default:             # needs: internet-gateway
    associations:
      - public-1a
      - public-1b
  private:
    route-default:             # needs: nat-gateway
    associations:
      - private-1a
      - private-1b

outputs:
  vpcId:
  subnets:
    public-1a:
    public-1b:
    private-1a:
    private-1b:
```

**Definitions:** [vpc](2026-08-20-resource-dictionary/vpc.md) · [subnets](2026-08-20-resource-dictionary/subnets.md) · [internet-gateway](2026-08-20-resource-dictionary/internet-gateway.md) · [nat-elastic-ip](2026-08-20-resource-dictionary/nat-elastic-ip.md) · [nat-gateway](2026-08-20-resource-dictionary/nat-gateway.md) · [route-tables](2026-08-20-resource-dictionary/route-tables.md) · [route-default](2026-08-20-resource-dictionary/route-default.md) · [associations](2026-08-20-resource-dictionary/associations.md)

## 02 · iam

```yaml
eks-cluster-role:
  eks-cluster-policy:

eks-node-role:
  node-policies:
    - worker
    - ecr
    - cni
```

**Definitions:** [eks-cluster-role](2026-08-20-resource-dictionary/eks-cluster-role.md) · [eks-cluster-policy](2026-08-20-resource-dictionary/eks-cluster-policy.md) · [eks-node-role](2026-08-20-resource-dictionary/eks-node-role.md) · [node-policies](2026-08-20-resource-dictionary/node-policies.md)

## 03 · eks

```yaml
eks-cluster:                   # needs: eks-cluster-role, subnets
  eks-node-group:              # needs: eks-node-role, subnets/private
  addon-pod-identity-agent:
  cluster-auth:                # → Secret kubeconfig
    provider-configs:
      - helm
      - kubernetes
  access-entry-crossplane:     # needs: crossplaneArn (hub)
    access-policy-crossplane:  # needs: crossplaneArn (hub)
  ebs-csi-driver:
    role:
    policy:
    association:
    addon:

outputs:
  Secret-kubeconfig:
  provider-configs:
  addon-pod-identity-agent:
```

**Definitions:** [eks-cluster](2026-08-20-resource-dictionary/eks-cluster.md) · [eks-node-group](2026-08-20-resource-dictionary/eks-node-group.md) · [addon-pod-identity-agent](2026-08-20-resource-dictionary/addon-pod-identity-agent.md) · [cluster-auth](2026-08-20-resource-dictionary/cluster-auth.md) · [provider-configs](2026-08-20-resource-dictionary/provider-configs.md) · [access-entry-crossplane](2026-08-20-resource-dictionary/access-entry-crossplane.md) · [access-policy-crossplane](2026-08-20-resource-dictionary/access-policy-crossplane.md) · [ebs-csi-driver](2026-08-20-resource-dictionary/ebs-csi-driver.md)

## 04 · dns

```yaml
route53-hosted-zone:
  records:
    delegation:                # on the parent zone · gate: subzone nameServers
    wildcard:                  # needs: nlb-hostname-observer · gate: NLB hostname

nlb-hostname-observer:         # needs: provider-configs/kubernetes · observes: istio-ingress-gateway (hostname)

outputs:
  zoneId:
```

**Definitions:** [route53-hosted-zone](2026-08-20-resource-dictionary/route53-hosted-zone.md) · [records](2026-08-20-resource-dictionary/records.md) · [nlb-hostname-observer](2026-08-20-resource-dictionary/nlb-hostname-observer.md)

## 05 · platform  (Releases via provider-configs/helm)

```yaml
aws-load-balancer-controller:  # +identity(role, policy, association) · gate: vpcId
  external-dns:                # +identity(role, association, policy-route53) · gate: alb ready, zoneId
  cert-manager:                # +identity(role, association, policy-route53) · gate: alb ready
  istio-base:                  # gate: alb ready
    istiod:
      istio-ingress-gateway:   # → NLB
```

**Definitions:** [aws-load-balancer-controller](2026-08-20-resource-dictionary/aws-load-balancer-controller.md) · [external-dns](2026-08-20-resource-dictionary/external-dns.md) · [cert-manager](2026-08-20-resource-dictionary/cert-manager.md) · [istio-base](2026-08-20-resource-dictionary/istio-base.md) · [istiod](2026-08-20-resource-dictionary/istiod.md) · [istio-ingress-gateway](2026-08-20-resource-dictionary/istio-ingress-gateway.md)

## 06 · objects  (via provider-configs/kubernetes)

```yaml
cluster-issuer:                # needs: cert-manager · gate: zoneId
  certificate-wildcard:

echo:
  namespace:
  deployment:
  service:
  gateway:                     # needs: istio-ingress-gateway, certificate-wildcard
  virtualservice:              # needs: gateway, service

outputs:
  echo-url: https://echo.<zone>/get   # HTTP 200
```

**Definitions:** [cluster-issuer](2026-08-20-resource-dictionary/cluster-issuer.md) · [certificate-wildcard](2026-08-20-resource-dictionary/certificate-wildcard.md) · [echo](2026-08-20-resource-dictionary/echo.md)

---

## Fidelity notes on the monolith

- **Pod Identity (runtime, not order):** `addon-pod-identity-agent` (eks) delivers credentials at
  runtime to ALL associations (ebs-csi, alb, external-dns, cert-manager). It is created in parallel
  with the associations (does not block them); only on **teardown** does it stay alive until
  `aws-load-balancer-controller`.
- **`providerConfigName`:** every AWS MR receives `spec.providerConfigRef.name` (default `sandbox`,
  post-processing); Releases/Objects use the remote provider-configs. It is not a resource — it
  applies to all of them.
- **`access-policy-crossplane`** (AccessPolicyAssociation): the composition creates it with
  `clusterNameSelector + principalArn` (it does not reference the access-entry by selector), but the
  EKS API requires the access-entry beforehand — hence the nesting.

## Teardown = reverse order (06 → 01)

Dependencies **across layers** that require explicit ordering (`ClusterUsage`):

```yaml
network:                       # by eks-node-group (egress alive until pods leave)
addon-pod-identity-agent:      # by aws-load-balancer-controller (creds to delete the NLB)
provider-configs:              # by Releases/Objects (uninstall via kubeconfig)
aws-load-balancer-controller:  # by istio-ingress-gateway (NLB disappears first)
```

## Porting notes

- The monolith defaults `providerConfigName` to `sandbox`; in this repo `sandbox` is retired,
  `providerConfigName` is mandatory, and the enum is `[network, wasp-nonprod]` — there is no
  default ProviderConfig.
- The monolith hardcodes the VPC CIDR `172.16.0.0/16`; this repo allocates from the supernet
  `10.0.0.0/12`, one `/16` per spoke — do not inherit the hardcoded value.
- The layer numbering here describes the monolith's internal ordering, not this repo's Terraform
  layers.
