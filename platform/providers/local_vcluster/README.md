# Provider local de Environment (vcluster)

Atende a capacidade `Environment` no target local: cada `Environment` do namespace `platform-system` vira um [vcluster](https://www.vcluster.com/) (release Helm `vcluster`) no namespace `env-<nome>` do próprio `platform-local`.

Roda **dentro do cluster**, como Deployment `local-vcluster-provider` em `platform-system`, instalado pelo `platform init --target local`. Não precisa de Docker nem de processo no host.

## Reconciliação

- Adiciona o finalizer `platform.wasp.silvios.me/local-vcluster`.
- Escolhe uma porta livre da faixa `7100`–`7119` (portas já usadas por Services `app=vcluster` do tipo LoadBalancer) e a grava em `status.port`.
- Instala o chart `vcluster` com o certificado válido para `127.0.0.1` (`helm.py`, `values()`). O Service do chart fica no padrão, ClusterIP na `443`: o vcluster espelha as portas dele no `kubernetes` Service virtual e injeta `KUBERNETES_SERVICE_PORT=443` nos pods, então mudar essa porta deixa o CoreDNS sem API e o DNS do ambiente quebrado (#307). A porta do host fica num segundo Service, `vcluster-host` (`LoadBalancer`), criado pelo próprio chart (`experimental.deploy.host.manifests`) e removido com ele. O `init` mapeia a faixa no load balancer do k3d, então a API do ambiente responde em `https://127.0.0.1:<porta>` no host, e dentro do `platform-local` em `https://vcluster.env-<nome>`.
- Quando o vcluster grava o Secret `vc-vcluster` (com o kubeconfig apontando para `127.0.0.1:<porta>`), instala o mesh dentro dele (ADR 0035, `mesh.py`): os CRDs standard do Gateway API por server-side apply, depois `istio/base` e `istio/istiod` por `helm upgrade --install` no namespace `istio-system`, contra `https://vcluster.env-<nome>`. Grava as versões em `status.mesh` e espera o Deployment `istiod` ficar disponível (`Provisioning`, "waiting for istiod in the vcluster"). Um ambiente sem `status.mesh` (criado antes do mesh) recebe a instalação na próxima passada: ela não toca a release do vcluster, e os pods que já rodam ganham o sidecar no próximo deploy.
- Com o `istiod` pronto, copia o kubeconfig para `status.kubeconfigData` e marca `Ready=True, reason=ClusterReady`. A API devolve esse campo só no `GET` de um ambiente, e a CLI o grava em `~/.config/platform/environments/<nome>.kubeconfig`.
- Falhas viram `Ready=False, reason=ProvisioningFailed` com a mensagem (inclusive "todas as portas em uso").
- No delete, desinstala o release, apaga o namespace e remove o finalizer.
- Quando `spec.expiresAt` passa, apaga o `Environment`. Watch mais uma passada completa a cada 10 s (`--resync-seconds`), que também pega o Secret do kubeconfig de um vcluster recém-criado.

## Imagem

`Dockerfile`: Python + o binário `helm` (de `alpine/helm`) + o chart `vcluster` baixado no build (`VCLUSTER_CHART_VERSION`, hoje `0.37.2`) + os charts `istio/base` e `istio/istiod` (`ISTIO_VERSION`, hoje `1.30.5`) + o `standard-install.yaml` do Gateway API (`GATEWAY_API_VERSION`, hoje `v1.5.1`, a versão que o Istio 1.30 suporta: as duas andam juntas). O cluster não precisa alcançar `charts.loft.sh`, o repositório do Istio nem o GitHub em runtime. O `platform init` builda a imagem e a importa no k3d.

## Permissões

A ServiceAccount tem `cluster-admin`: o chart cria uma ClusterRole e um ClusterRoleBinding por vcluster. Aceitável no target local; um target compartilhado precisaria de um caminho mais restrito.

## Escolha (#183)

| | k3d no host (antes) | vcluster no `platform-local` |
|---|---|---|
| Criar até pronto | 7 s | ~30 s (~50 s com o mesh, ADR 0035) |
| Apagar | 4 s | < 1 s (namespace some em seguida) |
| Onde o provider roda | host, `platform provider run` em foreground | dentro do cluster, sempre |
| Expiração com ninguém olhando | não | sim |

Cluster API foi descartada para o local: o CAPD precisa do socket do Docker montado no cluster de gerência, e o `cluster-api-provider-vcluster` só tem versões alpha.

## Depurar

```bash
kubectl --context k3d-platform-local --namespace platform-system logs deploy/local-vcluster-provider
helm --kube-context k3d-platform-local list --all-namespaces
vcluster list --context k3d-platform-local
```

## Testes

```bash
cd platform/providers/local_vcluster
uv sync
uv run pytest
```
