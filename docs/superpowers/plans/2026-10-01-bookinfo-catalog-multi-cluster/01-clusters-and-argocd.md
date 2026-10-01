# Clusters and Central ArgoCD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Três k3d na rede `k3d-idp` — `idp-cluster-zero` (gestão, ArgoCD), `development` e `production` (apps) — com os dois de destino registrados no ArgoCD e lidos pelo Backstage.

**Architecture:** `cluster-create` passa a receber opções longas (nome, servers, porta da API, rede, porta de app). Um script novo `register-clusters` cria o ServiceAccount do ArgoCD em cada cluster de destino e o Secret de cluster no cluster-zero. `backstage-reader` ganha `--cluster`. `up` orquestra tudo. O ApplicationSet **não** é aplicado aqui (o layout do `gitops` muda no plano 02).

**Tech Stack:** k3d, ArgoCD (chart `argo/argo-cd` 10.2.1), Backstage kubernetes plugin.

**Spec:** `docs/superpowers/specs/2026-10-01-bookinfo-catalog-multi-cluster-design.md` — "Componentes › Clusters" e "Componentes › Backstage" (bloco `kubernetes`).

## Global Constraints

- Clusters: `idp-cluster-zero` 3 servers, API `6550`, portas `9080:80@loadbalancer` e `9443:443@loadbalancer` (ArgoCD); `development` 1 server, API `6551`, `9081:9080@loadbalancer`; `production` 1 server, API `6552`, `9082:9080@loadbalancer`.
- Rede Docker de todos: `k3d-idp`.
- Endereço do cluster de destino no ArgoCD e modo TLS: **o que o plano 00 registrou no spec** (risco 1). Este plano assume `https://k3d-<nome>-server-0:6443` com `insecure: false` + `caData`; se o spec registrar outro, usar o do spec e anotar a troca no ledger.
- Secret de cluster: nome `cluster-<nome>`, namespace `argocd`, labels `argocd.argoproj.io/secret-type: cluster` e `env: <nome>`.
- ServiceAccount do ArgoCD nos destinos: `kube-system/argocd-manager`, `ClusterRole cluster-admin`.
- Backstage: clusters `development` (`https://127.0.0.1:6551`) e `production` (`https://127.0.0.1:6552`); variáveis `K8S_DEVELOPMENT_TOKEN`/`K8S_DEVELOPMENT_CA`, `K8S_PRODUCTION_TOKEN`/`K8S_PRODUCTION_CA`.
- Scripts no padrão de `scripts/cluster-zero/install-argocd` (`#!/bin/bash`, `this_script_directory`, uma opção por linha).

## Review Focus

- `register-clusters` rodado duas vezes (idempotência): `kubectl apply` não falha e o token continua válido.
- `cluster-create` sem `--name`: deve falhar com mensagem de uso, não criar `k3s-default`.
- `backstage-reader --cluster inexistente`: deve falhar com mensagem clara (contexto ausente), não imprimir `export` vazio que o `eval` aceitaria.
- Rede `k3d-idp` já existente: `up` não pode falhar ao tentar criá-la de novo.
- Contexto corrente ao fim do `up`: `k3d-idp-cluster-zero` (scripts posteriores assumem isso).

---

### Task 1: `cluster-create` com opções longas

**Files:**
- Modify: `scripts/cluster-zero/cluster-create` (reescrita)

**Interfaces:**
- Produces: `cluster-create --name <nome> [--servers <n>] [--api-port <porta>] [--network <rede>] [--app-port <porta>]`. Sem `--app-port`: mapeia `9080:80` e `9443:443` (ArgoCD). Com `--app-port <p>`: mapeia `<p>:9080@loadbalancer`. Defaults: `--servers 1`, `--network k3d-idp`. `--api-port` obrigatório.

- [ ] **Step 1: Teste que falha**

Run: `scripts/cluster-zero/cluster-create --name x 2>&1 | head -3; echo "exit=${PIPESTATUS[0]}"`
Expected: com o script atual o `--name` vira nome de cluster literal e o k3d tenta criar `--name` — falha de forma não controlada (ou cria cluster errado: nesse caso apagar com `k3d cluster delete -- --name`). O comportamento novo esperado é `--api-port is required` e exit ≠ 0.

- [ ] **Step 2: Reescrever `scripts/cluster-zero/cluster-create`**

```bash
#!/bin/bash
set -e

show_usage() {
  cat <<EOF
Usage: ${0##*/} --name <name> --api-port <port> [--servers <n>] [--network <network>] [--app-port <port>]

  --name       k3d cluster name (kubectl context becomes k3d-<name>)
  --api-port   host port for the Kubernetes API
  --servers    number of server nodes (default: 1)
  --network    Docker network shared by the clusters (default: k3d-idp)
  --app-port   host port mapped to load balancer port 9080 (apps);
               without it, host 9080/9443 map to 80/443 (ArgoCD)
EOF
}

cluster_name=""
api_port=""
servers="1"
network="k3d-idp"
app_port=""

while [[ "$#" -gt 0 ]]; do
  case "${1}" in
    --name) cluster_name="${2?}"; shift 2 ;;
    --api-port) api_port="${2?}"; shift 2 ;;
    --servers) servers="${2?}"; shift 2 ;;
    --network) network="${2?}"; shift 2 ;;
    --app-port) app_port="${2?}"; shift 2 ;;
    --help) show_usage; exit 0 ;;
    *) echo "Unknown option: ${1}" >&2; show_usage >&2; exit 1 ;;
  esac
done

if [[ -z "${cluster_name}" ]]; then
  echo "--name is required" >&2
  show_usage >&2
  exit 1
fi

if [[ -z "${api_port}" ]]; then
  echo "--api-port is required" >&2
  show_usage >&2
  exit 1
fi

if [[ -n "${app_port}" ]]; then
  port_options=(--port "${app_port}:9080@loadbalancer")
else
  port_options=(--port "9080:80@loadbalancer" --port "9443:443@loadbalancer")
fi

docker network inspect "${network}" > /dev/null 2>&1 \
  || docker network create "${network}" > /dev/null

echo ""
echo "Creating k3d cluster '${cluster_name}' (${servers} servers, API ${api_port}, network ${network})..."

k3d cluster create \
  "${cluster_name}" \
  --api-port "${api_port}" \
  "${port_options[@]}" \
  --servers "${servers}" \
  --network "${network}" \
  --k3s-arg '--disable=traefik@server:*' \
  --wait \
  --timeout 360s

kubectl wait node \
  --context "k3d-${cluster_name}" \
  --selector kubernetes.io/os=linux \
  --for condition=Ready \
  --timeout=360s

kubectl wait deployment metrics-server \
  --context "k3d-${cluster_name}" \
  --namespace kube-system \
  --for condition=Available \
  --timeout=360s

sleep 2

kubectl wait pods \
  --context "k3d-${cluster_name}" \
  --namespace kube-system \
  --selector k8s-app=metrics-server \
  --for condition=Ready \
  --timeout=360s

echo ""
echo "Cluster '${cluster_name}' ready."
```

- [ ] **Step 3: Validação de argumentos**

Run: `scripts/cluster-zero/cluster-create --name x; echo "exit=$?"; scripts/cluster-zero/cluster-create; echo "exit=$?"`
Expected: `--api-port is required` / `--name is required`, ambos `exit=1`; `k3d cluster list` sem cluster novo.

- [ ] **Step 4: Recriar os três clusters**

```bash
k3d cluster delete idp-cluster-zero 2> /dev/null || true
scripts/cluster-zero/cluster-create --name development --api-port 6551 --app-port 9081
scripts/cluster-zero/cluster-create --name production --api-port 6552 --app-port 9082
scripts/cluster-zero/cluster-create --name idp-cluster-zero --api-port 6550 --servers 3
k3d cluster list
docker network inspect k3d-idp --format '{{range .Containers}}{{.Name}} {{end}}'
docker port k3d-development-serverlb; docker port k3d-production-serverlb
```

Expected: três clusters; todos os containers na rede `k3d-idp`; `9080/tcp -> 0.0.0.0:9081` no serverlb de development e `-> 0.0.0.0:9082` no de production.

- [ ] **Step 5: shellcheck e commit**

```bash
docker run --rm --volume "${PWD}:/mnt" --workdir /mnt koalaman/shellcheck:stable scripts/cluster-zero/cluster-create
git add scripts/cluster-zero/cluster-create
git commit --message "feat(#105): cluster-create com opções de nome, rede e porta de app"
```

### Task 2: ArgoCD no cluster-zero e `register-clusters`

**Files:**
- Create: `scripts/cluster-zero/register-clusters`

**Interfaces:**
- Consumes: contextos `k3d-idp-cluster-zero`, `k3d-development`, `k3d-production` (Task 1); `server`/TLS do plano 00.
- Produces: Secrets `argocd/cluster-development` e `argocd/cluster-production` com label `env` — selecionados pelo gerador `clusters` do ApplicationSet no plano 02.

- [ ] **Step 1: ArgoCD**

```bash
kubectl config use-context k3d-idp-cluster-zero
scripts/cluster-zero/install-argocd
```

- [ ] **Step 2: Teste que falha**

Run: `kubectl --context k3d-idp-cluster-zero --namespace argocd get secret --selector argocd.argoproj.io/secret-type=cluster --output name`
Expected: vazio.

- [ ] **Step 3: `scripts/cluster-zero/register-clusters`**

```bash
#!/bin/bash
# Register the development and production k3d clusters as ArgoCD destinations
# in idp-cluster-zero. Idempotent: re-running refreshes the cluster Secrets.
set -e

management_context="k3d-idp-cluster-zero"
namespace="kube-system"
account="argocd-manager"

for cluster in development production; do
  context="k3d-${cluster}"

  if ! kubectl config get-contexts "${context}" > /dev/null 2>&1; then
    echo "kubectl context ${context} not found; create the cluster first" >&2
    exit 1
  fi

  echo ""
  echo "Ensuring ServiceAccount ${namespace}/${account} in ${cluster}..."

  kubectl --context "${context}" apply --filename - > /dev/null <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ${account}
  namespace: ${namespace}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ${account}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: ${account}
    namespace: ${namespace}
---
apiVersion: v1
kind: Secret
metadata:
  name: ${account}-token
  namespace: ${namespace}
  annotations:
    kubernetes.io/service-account.name: ${account}
type: kubernetes.io/service-account-token
EOF

  kubectl wait \
    --context "${context}" \
    --namespace "${namespace}" \
    --for jsonpath='{.data.token}' \
    --timeout=60s \
    "secret/${account}-token" > /dev/null

  token="$(
    kubectl get secret "${account}-token" \
      --context "${context}" \
      --namespace "${namespace}" \
      --output jsonpath='{.data.token}' \
    | base64 --decode
  )"

  ca="$(
    kubectl get secret "${account}-token" \
      --context "${context}" \
      --namespace "${namespace}" \
      --output jsonpath='{.data.ca\.crt}'
  )"

  echo "Registering ${cluster} in ArgoCD (token ${token:0:3}...)..."

  kubectl --context "${management_context}" apply --filename - > /dev/null <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: cluster-${cluster}
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: cluster
    env: ${cluster}
type: Opaque
stringData:
  name: ${cluster}
  server: https://k3d-${cluster}-server-0:6443
  config: |
    {"bearerToken": "${token}", "tlsClientConfig": {"insecure": false, "caData": "${ca}"}}
EOF
done

echo ""
echo "Registered clusters:"
kubectl \
  --context "${management_context}" \
  --namespace argocd \
  get secret \
  --selector argocd.argoproj.io/secret-type=cluster \
  --output custom-columns=NAME:.metadata.name,ENV:.metadata.labels.env
```

```bash
chmod +x scripts/cluster-zero/register-clusters
```

- [ ] **Step 4: Rodar duas vezes e provar conectividade**

```bash
scripts/cluster-zero/register-clusters
scripts/cluster-zero/register-clusters
for cluster in development production; do
kubectl --context k3d-idp-cluster-zero apply --filename - <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: probe-${cluster}
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/argoproj/argocd-example-apps.git
    targetRevision: HEAD
    path: guestbook
  destination:
    name: ${cluster}
    namespace: probe
  syncPolicy:
    automated: {}
    syncOptions:
      - CreateNamespace=true
EOF
kubectl --context k3d-idp-cluster-zero --namespace argocd wait "application/probe-${cluster}" --for jsonpath='{.status.sync.status}'=Synced --timeout=240s
kubectl --context "k3d-${cluster}" --namespace probe get deploy guestbook-ui
done
```

Expected: segunda execução sem erro; as duas Applications `Synced`; `guestbook-ui` existe em cada cluster.

Desfazer a prova:

```bash
kubectl --context k3d-idp-cluster-zero --namespace argocd delete application probe-development probe-production
kubectl --context k3d-development delete namespace probe
kubectl --context k3d-production delete namespace probe
```

- [ ] **Step 5: Contexto ausente**

Run: `KUBECONFIG=/nonexistent scripts/cluster-zero/register-clusters; echo "exit=$?"`
Expected: `kubectl context k3d-development not found; create the cluster first`, `exit=1`.

- [ ] **Step 6: shellcheck e commit**

```bash
docker run --rm --volume "${PWD}:/mnt" --workdir /mnt koalaman/shellcheck:stable scripts/cluster-zero/register-clusters
git add scripts/cluster-zero/register-clusters
git commit --message "feat(#105): registrar development e production no ArgoCD do cluster-zero"
```

### Task 3: Backstage lê `development` e `production`

**Files:**
- Modify: `scripts/cluster-zero/backstage-reader`
- Modify: `idp/app-config.yaml` (bloco `kubernetes:`)

**Interfaces:**
- Produces: `backstage-reader --cluster <nome>` imprime `export K8S_<NOME>_TOKEN='...'` e `export K8S_<NOME>_CA='...'` (`<NOME>` = nome em maiúsculas). Uso: `eval "$(scripts/cluster-zero/backstage-reader --cluster development)"; eval "$(scripts/cluster-zero/backstage-reader --cluster production)"`.

- [ ] **Step 1: Teste que falha**

Run: `scripts/cluster-zero/backstage-reader --cluster development 2>/dev/null | head -1`
Expected: `export K8S_CLUSTER_ZERO_TOKEN=...` (o script atual ignora o argumento e usa o contexto corrente) — errado.

- [ ] **Step 2: Editar `backstage-reader`** — acrescentar parsing de `--cluster` (obrigatório), checar o contexto, passar `--context "k3d-${cluster}"` a todo `kubectl` e trocar os nomes das variáveis. Trechos novos/alterados:

```bash
#!/bin/bash
# Create (idempotently) a read-only ServiceAccount for the Backstage kubernetes
# plugin in one k3d cluster and print the environment variables it needs. Usage:
#   eval "$(scripts/cluster-zero/backstage-reader --cluster development)"
set -e

cluster=""

while [[ "$#" -gt 0 ]]; do
  case "${1}" in
    --cluster) cluster="${2?}"; shift 2 ;;
    *) echo "Unknown option: ${1}" >&2; exit 1 ;;
  esac
done

if [[ -z "${cluster}" ]]; then
  echo "Usage: ${0##*/} --cluster <name>" >&2
  exit 1
fi

context="k3d-${cluster}"

if ! kubectl config get-contexts "${context}" > /dev/null 2>&1; then
  echo "kubectl context ${context} not found" >&2
  exit 1
fi

variable_prefix="K8S_${cluster^^}"
variable_prefix="${variable_prefix//-/_}"

namespace="kube-system"
account="backstage-reader"
```

Em cada `kubectl` existente (`apply`, `wait`, os dois `get secret`), acrescentar `--context "${context}"`. As duas últimas linhas passam a ser:

```bash
echo "export ${variable_prefix}_TOKEN='${token}'"
echo "export ${variable_prefix}_CA='${ca}'"
```

- [ ] **Step 3: Rodar**

```bash
eval "$(scripts/cluster-zero/backstage-reader --cluster development)"
eval "$(scripts/cluster-zero/backstage-reader --cluster production)"
echo "${K8S_DEVELOPMENT_TOKEN:0:3} ${K8S_DEVELOPMENT_CA:0:3} ${K8S_PRODUCTION_TOKEN:0:3} ${K8S_PRODUCTION_CA:0:3}"
scripts/cluster-zero/backstage-reader --cluster nope; echo "exit=$?"
scripts/cluster-zero/backstage-reader; echo "exit=$?"
```

Expected: quatro prefixos não vazios (`eyJ`/`LS0`); `kubectl context k3d-nope not found` exit 1; uso exit 1, sem nenhuma linha `export` no stdout desses dois.

- [ ] **Step 4: `idp/app-config.yaml`** — substituir o item `cluster-zero` da lista `clusters` e o comentário acima de `serviceLocatorMethod`:

```yaml
kubernetes:
  # see https://backstage.io/docs/features/kubernetes/configuration for kubernetes configuration options
  # Local k3d clusters from scripts/cluster-zero. Credentials, before yarn start:
  #   eval "$(scripts/cluster-zero/backstage-reader --cluster development)"
  #   eval "$(scripts/cluster-zero/backstage-reader --cluster production)"
  serviceLocatorMethod:
    type: multiTenant
  clusterLocatorMethods:
    - type: config
      clusters:
        - name: development
          url: https://127.0.0.1:6551
          authProvider: serviceAccount
          serviceAccountToken: ${K8S_DEVELOPMENT_TOKEN}
          caData: ${K8S_DEVELOPMENT_CA}
        - name: production
          url: https://127.0.0.1:6552
          authProvider: serviceAccount
          serviceAccountToken: ${K8S_PRODUCTION_TOKEN}
          caData: ${K8S_PRODUCTION_CA}
```

- [ ] **Step 5: Verificar pelo backend** — reiniciar o Backstage com as variáveis (parar pelos PIDs de `:3000`/`:7007`), depois:

```bash
token="$(curl --silent localhost:7007/api/auth/guest/refresh | python3 -c 'import sys,json;print(json.load(sys.stdin)["backstageIdentity"]["token"])')"
curl --silent --header "Authorization: Bearer ${token}" localhost:7007/api/kubernetes/clusters
```

Expected: `development` e `production`, ambos `authProvider: serviceAccount`. Log do backend sem `kubernetes` + `401`/`certificate`.

- [ ] **Step 6: shellcheck e commit**

```bash
docker run --rm --volume "${PWD}:/mnt" --workdir /mnt koalaman/shellcheck:stable scripts/cluster-zero/backstage-reader
git add scripts/cluster-zero/backstage-reader idp/app-config.yaml
git commit --message "feat(#105): Backstage lê os clusters development e production"
```

### Task 4: `up` e documentação

**Files:**
- Modify: `scripts/cluster-zero/up`
- Modify: `scripts/cluster-zero/cluster-delete`
- Modify: `docs/idp/CLAUDE.md` (tabela `## Scripts`)

- [ ] **Step 1: `up`**

```bash
#!/bin/bash
set -e

this_script_path="$(realpath "${0}")"
this_script_directory="${this_script_path%/*}"

PATH="${this_script_directory}:${PATH}"

check-prereqs
cluster-create --name development --api-port 6551 --app-port 9081
cluster-create --name production --api-port 6552 --app-port 9082
cluster-create --name idp-cluster-zero --api-port 6550 --servers 3
kubectl config use-context k3d-idp-cluster-zero
install-argocd
install-crossplane
register-clusters
verify
```

- [ ] **Step 2: `cluster-delete`** — sem argumento apaga os três:

```bash
#!/bin/bash

if [[ "$#" -eq 0 ]]; then
  set -- idp-cluster-zero development production
fi

echo ""
echo "Deleting k3d clusters: $*..."

k3d cluster delete "$@"

echo ""

k3d cluster list
```

- [ ] **Step 3: Provar do zero**

```bash
scripts/cluster-zero/cluster-delete
scripts/cluster-zero/up > /tmp/up.log 2>&1; echo "exit=$?"; tail -5 /tmp/up.log
kubectl config current-context
kubectl --namespace argocd get secret --selector argocd.argoproj.io/secret-type=cluster --output name
```

Expected: `exit=0`; contexto `k3d-idp-cluster-zero`; `secret/cluster-development` e `secret/cluster-production`. Rodar `up` exige ~10 min; usar `run_in_background` ou `nohup`.

- [ ] **Step 4: Doc** — na tabela de `## Scripts` de `docs/idp/CLAUDE.md`: atualizar a linha de `cluster-create` (opções `--name`/`--api-port`/`--servers`/`--network`/`--app-port`), a de `cluster-delete` (sem argumento apaga os três) e a de `backstage-reader` (`--cluster <nome>`, uma chamada por cluster); acrescentar:

```markdown
| `scripts/cluster-zero/register-clusters` | Registers `development` and `production` as ArgoCD destinations in `idp-cluster-zero` (ServiceAccount `argocd-manager` + cluster Secret with label `env`) — idempotent |
```

- [ ] **Step 5: shellcheck e commit**

```bash
docker run --rm --volume "${PWD}:/mnt" --workdir /mnt koalaman/shellcheck:stable scripts/cluster-zero/up scripts/cluster-zero/cluster-delete
git add scripts/cluster-zero/up scripts/cluster-zero/cluster-delete docs/idp/CLAUDE.md
git commit --message "feat(#105): up cria os três clusters e registra os destinos no ArgoCD"
```
