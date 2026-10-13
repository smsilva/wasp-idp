# Environment pod security enforced by a host admission policy

**Status:** Aceito (2026-10-13)

## Contexto

Cada `Environment` é um vcluster criado pelo provider `local_vcluster`, e quem pode usá-lo recebe `cluster-admin` dentro dele (ADR 0028). O vcluster não aplicava nenhum Pod Security Standard: os pods criados nele são sincronizados para o namespace `env-<name>` do host com o `spec` intacto, então um pod com `hostNetwork`, `privileged` ou `hostPath` roda assim no nó do host. Revisando a #411, um pod `hostNetwork` alcançou o Prometheus de `platform-system` (a NetworkPolicy dele admite só a `platform-api`, mas o tráfego sai do IP do nó, que o kube-router deixa passar) e, com ele, qualquer serviço do host e o próprio nó (#414).

Duas restrições moldam a escolha:

- **O `baseline` puro quebra o mesh.** O Istio roda sem CNI (ADR 0035), então todo pod com sidecar tem o init container `istio-init` com `NET_ADMIN` e `NET_RAW`, fora da lista de capabilities do `baseline`.
- **O PodSecurity admission dentro do vcluster não é uma fronteira.** `policies.podSecurityStandard` do chart só define o nível padrão; um `cluster-admin` do vcluster põe `pod-security.kubernetes.io/enforce=privileged` num namespace e o anula.

## Decisão

**A fronteira é uma `ValidatingAdmissionPolicy` no host, ligada aos pods que o vcluster sincroniza; a mesma policy dentro de cada vcluster só antecipa a recusa.**

- **Regras:** as do `baseline` em CEL (sem `hostNetwork`, `hostPID`, `hostIPC`, `privileged`, `hostProcess`, `hostPath`, `hostPort`, `procMount` fora de `Default`, seccomp ou AppArmor `Unconfined`, SELinux além dos tipos de container, sysctls fora da lista segura), com uma diferença: `capabilities.add` aceita também `NET_ADMIN` e `NET_RAW`. Sem `hostNetwork`, elas só alcançam o network namespace do próprio pod.
- **No host:** `platform/providers/local_vcluster/deploy/pod-security.yaml`, aplicado pelo `platform init`. O binding seleciona pods com o label `vcluster.loft.sh/managed-by`, que o syncer põe em todo pod sincronizado; o control plane do vcluster não o tem e fica de fora. Vale para os ambientes já criados assim que o `init` roda.
- **No vcluster:** o provider instala a mesma policy, com um binding sem seletor, antes do mesh, e grava a versão (hash do arquivo) em `status.podSecurity`. Uma policy nova chega aos ambientes existentes no próximo reconcile, sem `helm upgrade`. O usuário pode apagar essa cópia; o host continua recusando, e o pod fica `Pending` no vcluster com o erro de sync em vez de falhar no `apply`.

## Alternativas consideradas

- **`policies.podSecurityStandard: baseline` no chart.** Quebra todo pod com sidecar e pode ser anulado por `cluster-admin`. Rejeitada.
- **`restricted`.** Exige `runAsNonRoot` e `drop: [ALL]`, o que o `istio-init` e muitas imagens públicas não cumprem. Rejeitada.
- **Istio CNI no host, para eliminar o `istio-init`.** Permitiria o `baseline` puro, mas é um DaemonSet privilegiado mexendo na configuração de CNI do nó compartilhado por todos os ambientes, com istiod em cada vcluster. Escopo bem maior; rejeitada por ora.
- **PSA por label no namespace `env-<name>` do host.** O label vale também para o control plane do vcluster e não aceita a exceção de capabilities. Rejeitada.

## Consequências

- Um pod que pede acesso ao host é recusado com a mensagem da regra, no `kubectl apply` dentro do vcluster e, como garantia, quando o syncer o cria no host.
- Imagens que dependem de `SYS_ADMIN`, `hostPath` ou `privileged` (agentes de nó, alguns operadores de storage) não rodam num ambiente.
- A policy vale só para o target local; um target em nuvem com vclusters precisa da mesma policy no cluster de controle.
