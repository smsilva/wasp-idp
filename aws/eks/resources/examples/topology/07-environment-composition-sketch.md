# ESBOÇO (não implementado) — `environment/composition.yaml` orquestrando Network + Cluster
# + N NodeGroups a partir de 1 claim `Environment`.

Ponto central: com NodeGroup virando abstração própria e `nodeGroups` sendo uma LISTA no
`Environment.spec`, o orquestrador precisa compor um número VARIÁVEL de filhos (1 Network +
1 Cluster + N NodeGroups). `function-patch-and-transform` tem `resources` ESTÁTICO (lista
fixa de recursos no input da Composition) — ele NÃO itera sobre um array do composite. Isso
é o mesmo caveat de array que já apareceu no 06-environment-orchestrator-patch.md, agora mais agudo.

## Duas formas de compor N NodeGroups

### Opção A — function-kcl no orquestrador (fan-out real)
KCL itera sobre `spec.nodeGroups` e emite 1 XR `NodeGroup` por item:

```python
# pseudo-KCL
items = option("params").oxr.spec.nodeGroups
_nodegroups = [{
    apiVersion = "platform.example.com/v1alpha1"
    kind = "NodeGroup"
    metadata.name = "{}-{}".format(oxr.metadata.name, ng.name)
    spec = {
        clusterRef.name = oxr.metadata.name
        subnetIds = oxr.status.subnetIdsPrivate   # resolvido do Network
        instanceType = ng.instanceType
        capacityType = ng?.capacityType or "ON_DEMAND"
        desiredSize = ng.desiredSize
        minSize = ng.minSize
        maxSize = ng.maxSize
    }
} for ng in items]
```

- Prós: fan-out de verdade (N variável), monta arrays de subnet nativamente (resolve os 2
  caveats de uma vez). function-kcl já está instalada no hub.
- Contras: o orquestrador deixa de ser patch-and-transform puro; introduz KCL nesta camada.

### Opção B — patch-and-transform com slots fixos
Declarar no `resources` um número MÁXIMO de NodeGroups (ex.: 3 slots), cada um com um patch
que só "liga" se `spec.nodeGroups[i]` existir. Feio, teto artificial, patches condicionais
frágeis. Descartar — só listado para registro.

## Estrutura do pipeline (Opção A)

```yaml
mode: Pipeline
pipeline:
  - step: fan-out
    functionRef:
      name: function-kcl
    input:
      # KCL: 1 Network + 1 Cluster + N NodeGroups, todos derivados de oxr.metadata.name.
      # Cluster.subnetIds  <- Network.status.subnetIds (todas as 4)
      # NodeGroup.subnetIds <- Network.status.subnetIds (só privadas)
      # Espera o Network status estar populado (ordenação por readiness da Composition).
  - step: auto-ready
    functionRef:
      name: function-auto-ready
```

O crossplaneArn (EnvironmentConfig) continua necessário no Cluster — ou o step
function-environment-configs entra aqui também, ou o Cluster resolve isso na SUA própria
Composition (mais provável: o Cluster já faz isso hoje, o Environment não precisa saber).

## Ordenação Network -> Cluster/NodeGroup

O Cluster precisa das subnetIds do Network ANTES de existir. Com fan-out KCL, o Cluster só
recebe subnetIds válidos quando `Network.status.subnetIds` estiver populado. Enquanto vazio,
o KCL emite o Cluster sem subnetIds (inválido) OU o omite até o status chegar. Verificar na
implementação se function-kcl consegue condicionar a emissão do Cluster à presença do status
do Network (provavelmente sim: `if oxr.status?.subnetIds`). Este é o mesmo tipo de
dependência intra-Composition que o modelo atual resolve com selector (que espera
naturalmente). Trade-off a medir no hub.
