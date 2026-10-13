# Provider workload

Aplica cada `WorkloadRevision` no vcluster do seu `Environment` e mantém a `WorkloadInstance` ([ADR 0033](../../../docs/adr/0033-workload-spec-and-workload-instance.md), #292). Transforma cada `WorkloadRoute` num `HTTPRoute` GAMMA no mesmo vcluster ([ADR 0035](../../../docs/adr/0035-istio-sidecar-per-environment-vcluster-gamma-routes.md), #344). Funciona com qualquer `Environment` `Ready` que tenha `status.kubeconfigData`, sem depender do `local_vcluster`.

Roda **dentro do cluster**, como Deployment `workload-provider` em `platform-system`, instalado pelo `platform init --target local`.

## Reconciliação

- A cada passada, lista revisões e instâncias. Por instância (`<environment>.<instance>`), só a revisão mais nova conta: uma mais antiga ainda aberta fecha como `Superseded`.
- Revisão aberta (`Ready` ausente ou `Unknown`): lê o `Environment` (sem `Ready` vira `EnvironmentNotReady`, que segue aberta) e a `Version` (`<component>.<version>`). Gera Namespace `apps`, Deployment e Service a partir do Score (`manifests.py`), aplica com server-side apply (field manager `platform-workload`) e acompanha o rollout. Fecha como `Succeeded` ou `RolloutFailed` (o Deployment sai com `progressDeadlineSeconds: 120`) e cria ou atualiza a instância.
- Score com `resources`: a revisão fica aberta como `ResourcesPending` até cada recurso ter um `ResourceRequest` (`<environment>.<instance>.<resource>`, do Forager) resolvido para esta revisão (`status.revision`) e `Ready`. As saídas preenchem `${resources.<n>.<campo>}`, e um campo secreto vira `secretKeyRef`. A instância guarda o resumo em `status.resources`.
- Falhas finais, sem tocar no vcluster: `SpecNotIndexed`, `ResourcesNotSupported` (um recurso sem provisioner na política), `ResourceModeChanged`, `ResourcesFailed`, `UnsupportedSpec`. `ApplyFailed` quando o vcluster recusa ou não responde.
- Revisão `Succeeded` mais nova: atualiza réplicas e `Ready` da instância (`Available`, `Progressing`, `Degraded`) só quando mudam.
- Um watch de `workloadrevisions` e outro de `workloadroutes`, cada um numa thread, acordam a passada por um `threading.Event` quando um objeto é criado, apagado ou muda de `generation` (as escritas de status do próprio provider não mudam a `generation` e não acordam). Sem mudança, a passada seguinte vem em 5 s enquanto há revisão ou rota pendente (`--poll-seconds`) e em 30 s no resto do tempo (`--resync-seconds`).
- Revisões, instâncias e rotas têm owner reference para o `Environment`: somem com ele.

## Rotas

- Uma `WorkloadRoute` (`<environment>.<component>`, escrita pela Platform API) vira um `HTTPRoute` `apps/<component>` com `parentRef` no Service `<component>` (`routes.py`). Cada regra vira uma regra do `HTTPRoute`, na mesma ordem: header em `matches.headers`; baggage numa `RegularExpression` sobre o header `baggage` (a entrada `key=value` em qualquer posição, com `;propriedades` opcionais); pesos em `backendRefs` com `weight`. No fim, uma regra sem match manda o resto para `<component>`. A porta de cada `backendRef` é a primeira do Service da instância.
- `status.conditions[Ready]`: `Accepted` quando o mesh marca `Accepted` e `ResolvedRefs`; `Unknown` com `Pending` (o mesh ainda não olhou), `EnvironmentNotReady` ou `InstancePending` (uma instância ainda sem Service); `False` com `MeshNotInstalled` (ambiente criado antes do ADR 0035), `ApplyFailed` ou o motivo do `HTTPRoute`. `status.observedGeneration` diz qual versão da rota a condition descreve.
- Istio só aplica a rota a chamadas que saem de um pod com sidecar no namespace `apps`: um pod de teste precisa de `sleep` + `kubectl exec`, porque com sidecar ele nunca termina (`wait --for Succeeded` não serve). O match de header do Istio é RE2 de valor inteiro, por isso a regex do baggage tem prefixo/sufixo opcionais em vez de âncoras.
- O finalizer `platform.wasp.silvios.me/httproute` apaga o `HTTPRoute` antes da rota sair. Com o `Environment` sendo apagado (ou sem kubeconfig), o vcluster vai junto: o finalizer sai sem tocar nele.

## Acesso ao vcluster

Usa o kubeconfig admin de `Environment.status.kubeconfigData`, trocando o servidor (que aponta para `127.0.0.1`, para o host) por `https://vcluster.env-{name}` (o Service do chart, ClusterIP na 443, `--vcluster-server`), o mesmo endereço que a Platform API usa em `credentials.py`. Um client por ambiente fica em cache enquanto o kubeconfig não muda.

## Permissões

Role em `platform-system`: lê revisões e escreve o status delas; lê rotas, escreve o status delas e o finalizer (`patch`); cria, apaga e escreve o status das instâncias; lê `environments` e `versions.catalog`; lê e apaga `resourcerequests` (o `remove` apaga os da instância, e o finalizer do Forager desfaz cada recurso). Nada fora do namespace: o acesso ao vcluster vem do kubeconfig.

## Testes

```bash
uv sync
uv run pytest
```
