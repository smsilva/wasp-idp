# PROPOSTA (ainda não implementada) — patch do `Environment` montando subnetIds do Cluster
# a partir do `Network.status.subnetIds`, sem selector/lookup cross-XR.

Hoje (`environment/composition.yaml`) o orquestrador só repassa `id/prefix/region` iguais
para os dois filhos, e o cruzamento Network→Cluster acontece DENTRO da Composition do
Cluster, via `matchLabels env=<id>`. Com `subnetIds` diretos, o cruzamento passa a acontecer
AQUI, no orquestrador — um patch estático de campos conhecidos, sem lookup em runtime:

```yaml
resources:
  - name: network
    base:
      apiVersion: platform.example.com/v1alpha1
      kind: Network
    patches:
      - type: FromCompositeFieldPath
        fromFieldPath: spec.prefix
        toFieldPath: spec.prefix
      - type: FromCompositeFieldPath
        fromFieldPath: spec.region
        toFieldPath: spec.region
      - type: ToCompositeFieldPath
        fromFieldPath: status.vpcId
        toFieldPath: status.vpcId

  - name: cluster
    base:
      apiVersion: platform.example.com/v1alpha1
      kind: Cluster
    patches:
      - type: FromCompositeFieldPath
        fromFieldPath: spec.prefix
        toFieldPath: spec.prefix
      - type: FromCompositeFieldPath
        fromFieldPath: spec.region
        toFieldPath: spec.region
      - type: FromCompositeFieldPath
        fromFieldPath: spec.nodeGroup
        toFieldPath: spec.nodeGroup
      # --- cruzamento Network -> Cluster, agora aqui (sem selector) ---
      # 4 subnets (2 públicas + 2 privadas) para o EKS Cluster (endpoint público+privado)
      - type: CombineFromComposite
        combine:
          variables:
            - fromFieldPath: network.status.subnetIds.publicA
            - fromFieldPath: network.status.subnetIds.publicB
            - fromFieldPath: network.status.subnetIds.privateA
            - fromFieldPath: network.status.subnetIds.privateB
          strategy: string
          string: { fmt: "%s,%s,%s,%s" }   # patch-and-transform não monta array nativamente;
        toFieldPath: spec.subnetIds.clusterCsv  # via string+split, OU trocar por function-kcl
                                                 # (já instalada no hub) se precisar de array real
      # só as 2 privadas para o NodeGroup
      # (mesmo caveat de array acima)
```

## Caveat descoberto ao esboçar isto

`function-patch-and-transform` não tem um patch nativo "monte um array a partir de N campos
escalares do composite" — `CombineFromComposite` produz uma STRING (via `fmt`), não uma
lista YAML. Duas saídas, a decidir na implementação:

1. **Trocar o step do orquestrador para `function-kcl`** (já instalada no hub, usada em
   outra parte do repo) — ela monta o array de verdade em código KCL:
   `subnetIds.cluster = [network.status.subnetIds.publicA, ...]`. Mais direto, mas introduz
   uma linguagem a mais só neste orquestrador (hoje ele é patch-and-transform puro).
2. **Manter `patch-and-transform`, mas o `Network.status` já publicar os 2 arrays prontos**
   (`status.subnetIdsForCluster: [...]`, `status.subnetIdsForNodeGroup: [...]`) — o Network
   monta os arrays (ele já tem os 4 IDs individualmente via `ToCompositeFieldPath` dos MRs
   `Subnet`), e o orquestrador só faz `FromCompositeFieldPath` direto (array → array, sem
   combine). Mantém tudo em patch-and-transform; move a montagem para dentro do Network, que
   é quem já sabe a topologia (mais alinhado com "quem monta a rede decide o tier").

Opção 2 parece mais consistente com o resto do design (Network como fonte da verdade da
topologia) — mas array-of-arrays via `ToCompositeFieldPath` dentro do MR `Subnet` (que só
tem 1 ID cada) também precisa ser verificado: provavelmente exige 4 `ToCompositeFieldPath`
individuais (1 por subnet) escrevendo em índices de um array no status do Network, o que o
patch-and-transform normalmente suporta via path com índice fixo
(`status.subnetIdsForCluster[0]`, `[1]`, `[2]`, `[3]`).

**A decidir na implementação, não neste exemplo.**
