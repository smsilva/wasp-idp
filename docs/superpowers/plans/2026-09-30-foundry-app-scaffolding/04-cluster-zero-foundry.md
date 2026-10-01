# Cluster Zero Foundry Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O k3d do cluster-zero passa a fazer deploy de tudo que estiver em `wasp-foundry/gitops` `apps/*`, e o Backstage passa a ler esse cluster na aba Kubernetes.

**Architecture:** Um `ApplicationSet` (gerador Git directory, sem credencial — repo público) aplicado por um script novo; um segundo script cria um ServiceAccount read-only e imprime os `export` que o Backstage consome via `kubernetes.clusterLocatorMethods` no `app-config.yaml`.

**Tech Stack:** k3d, ArgoCD (chart `argo/argo-cd` 10.2.1, já em `scripts/cluster-zero/install-argocd`), ApplicationSet com `goTemplate`, Backstage kubernetes plugin.

**Spec:** `docs/superpowers/specs/2026-09-30-foundry-app-scaffolding-design.md` — seções "`scripts/cluster-zero/`" e "Credenciais". Issue [#101](https://github.com/smsilva/wasp-idp/issues/101).

## Global Constraints

- ApplicationSet: nome `foundry-apps`, namespace `argocd`, repo `https://github.com/wasp-foundry/gitops.git`, `revision: main`, `directories: apps/*`.
- Cada `Application`: nome = namespace = basename do diretório; `project: default`; sync automático com `prune` e `selfHeal`; `CreateNamespace=true`; finalizer `resources-finalizer.argocd.argoproj.io`.
- ServiceAccount `backstage-reader` em `kube-system`, `ClusterRole view`.
- Variáveis para o Backstage: `K8S_CLUSTER_ZERO_TOKEN`, `K8S_CLUSTER_ZERO_CA`. Cluster no Backstage: nome `cluster-zero`, URL `https://127.0.0.1:6550` (`--api-port 6550` em `scripts/cluster-zero/cluster-create`).
- Scripts seguem o padrão de `scripts/cluster-zero/install-argocd`: `#!/bin/bash`, `set -e`, `this_script_directory`, `assets_directory`, uma opção por linha.
- `scripts/cluster-zero/up` **não muda**.
- Pré-requisito: plano 01 (repo `wasp-foundry/gitops` existe). Independe do plano 03.

---

### Task 1: ApplicationSet `foundry-apps`

**Files:**
- Create: `scripts/cluster-zero/assets/foundry-appset.yaml`
- Create: `scripts/cluster-zero/install-foundry-appset`

- [x] **Step 1: Cluster no ar**

```bash
scripts/cluster-zero/check-prereqs
scripts/cluster-zero/cluster-create idp-cluster-zero
scripts/cluster-zero/install-argocd
```

(Crossplane não é necessário para este fluxo.)

- [x] **Step 2: Teste que falha**

Run: `kubectl --namespace argocd get applicationset foundry-apps`
Expected: `Error from server (NotFound)`.

- [x] **Step 3: `assets/foundry-appset.yaml`**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: foundry-apps
  namespace: argocd
spec:
  goTemplate: true
  goTemplateOptions: ["missingkey=error"]
  generators:
    - git:
        repoURL: https://github.com/wasp-foundry/gitops.git
        revision: main
        directories:
          - path: apps/*
  template:
    metadata:
      name: '{{ .path.basename }}'
      finalizers:
        - resources-finalizer.argocd.argoproj.io
    spec:
      project: default
      source:
        repoURL: https://github.com/wasp-foundry/gitops.git
        targetRevision: main
        path: '{{ .path.path }}'
      destination:
        server: https://kubernetes.default.svc
        namespace: '{{ .path.basename }}'
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
```

- [x] **Step 4: `install-foundry-appset`**

```bash
#!/bin/bash
set -e

this_script_path="$(realpath "${0}")"
this_script_directory="${this_script_path%/*}"

assets_directory="${this_script_directory}/assets"

echo ""
echo "Applying ApplicationSet foundry-apps (wasp-foundry/gitops apps/*)..."

kubectl apply \
  --filename "${assets_directory}/foundry-appset.yaml"

kubectl wait \
  --namespace argocd \
  --for jsonpath='{.status.conditions[?(@.type=="ResourcesUpToDate")].status}'=True \
  --timeout=120s \
  applicationset/foundry-apps

echo ""
echo "ApplicationSet foundry-apps installed."
echo "Applications generated so far:"
kubectl \
  --namespace argocd \
  get applications \
  --output name
```

```bash
chmod +x scripts/cluster-zero/install-foundry-appset
```

- [x] **Step 5: Rodar e ver passar**

```bash
scripts/cluster-zero/install-foundry-appset
kubectl --namespace argocd get applicationset foundry-apps --output jsonpath='{.status.conditions[?(@.type=="ErrorOccurred")].status}'
```

Expected: script conclui; condição `ErrorOccurred` = `False`. Com `apps/` vazio (só `.gitkeep`), nenhuma `Application` é gerada — correto.

Se o `kubectl wait` expirar porque a condição `ResourcesUpToDate` não existe nesta versão do controller, trocar a espera por `ErrorOccurred`=False e registrar a troca na mensagem de commit.

- [x] **Step 6: Prova com um diretório real** (throwaway, desfeito no fim)

```bash
probe_dir="$(mktemp --directory)"
gh repo clone wasp-foundry/gitops "${probe_dir}"
mkdir --parents "${probe_dir}/apps/probe"
cat > "${probe_dir}/apps/probe/kustomization.yaml" <<'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - configmap.yaml
EOF
cat > "${probe_dir}/apps/probe/configmap.yaml" <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: probe
data:
  hello: world
EOF
git -C "${probe_dir}" add apps/probe
git -C "${probe_dir}" commit --message "chore: applicationset probe"
git -C "${probe_dir}" push
```

Esperar até 3 min (polling padrão do ApplicationSet/ArgoCD) ou forçar:

```bash
kubectl --namespace argocd annotate applicationset foundry-apps argocd.argoproj.io/refresh=normal --overwrite
kubectl --namespace argocd wait application/probe --for jsonpath='{.status.sync.status}'=Synced --timeout=240s
kubectl --namespace probe get configmap probe
```

Expected: `Application probe` Synced; ConfigMap existe no namespace `probe`.

Desfazer:

```bash
git -C "${probe_dir}" rm -r apps/probe
git -C "${probe_dir}" commit --message "chore: remove applicationset probe"
git -C "${probe_dir}" push
kubectl --namespace argocd annotate applicationset foundry-apps argocd.argoproj.io/refresh=normal --overwrite
kubectl --namespace argocd wait application/probe --for=delete --timeout=240s
kubectl delete namespace probe
rm --recursive --force "${probe_dir}"
```

Expected: `Application probe` some (finalizer apagou o ConfigMap); namespace removido à mão — comportamento documentado no spec.

- [x] **Step 7: shellcheck**

```bash
docker run --rm --volume "${PWD}:/mnt" --workdir /mnt koalaman/shellcheck:stable scripts/cluster-zero/install-foundry-appset
```

- [x] **Step 8: Commit**

```bash
git add scripts/cluster-zero/assets/foundry-appset.yaml scripts/cluster-zero/install-foundry-appset
git commit --message "feat(#101): ApplicationSet foundry-apps no cluster-zero"
```

### Task 2: ServiceAccount de leitura para o Backstage

**Files:**
- Create: `scripts/cluster-zero/backstage-reader`

**Interfaces:**
- Produces: stdout com duas linhas `export K8S_CLUSTER_ZERO_TOKEN=...` e `export K8S_CLUSTER_ZERO_CA=...` — consumidas por `eval "$(scripts/cluster-zero/backstage-reader)"` antes do `yarn start`. Mensagens de progresso vão para stderr, para o `eval` não as executar.

- [x] **Step 1: Teste que falha**

Run: `kubectl auth can-i list pods --all-namespaces --as system:serviceaccount:kube-system:backstage-reader`
Expected: `no`.

- [x] **Step 2: `backstage-reader`**

```bash
#!/bin/bash
# Create (idempotently) a read-only ServiceAccount for the Backstage kubernetes
# plugin and print the environment variables it needs. Usage:
#   eval "$(scripts/cluster-zero/backstage-reader)"
set -e

namespace="kube-system"
account="backstage-reader"

echo "Ensuring ServiceAccount ${namespace}/${account} with ClusterRole view..." >&2

kubectl apply --filename - > /dev/null <<EOF
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
  name: view
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
  --namespace "${namespace}" \
  --for jsonpath='{.data.token}' \
  --timeout=60s \
  "secret/${account}-token" > /dev/null

token="$(
  kubectl get secret "${account}-token" \
    --namespace "${namespace}" \
    --output jsonpath='{.data.token}' \
  | base64 --decode
)"

ca="$(
  kubectl get secret "${account}-token" \
    --namespace "${namespace}" \
    --output jsonpath='{.data.ca\.crt}'
)"

echo "Token: ${token:0:3}... (export it with eval)" >&2

echo "export K8S_CLUSTER_ZERO_TOKEN='${token}'"
echo "export K8S_CLUSTER_ZERO_CA='${ca}'"
```

Nota: `ca.crt` fica em base64 (formato que o `caData` do Backstage espera); o token é decodificado.

```bash
chmod +x scripts/cluster-zero/backstage-reader
```

- [x] **Step 3: Rodar e ver passar**

```bash
eval "$(scripts/cluster-zero/backstage-reader)"
echo "${K8S_CLUSTER_ZERO_TOKEN:0:3} ${K8S_CLUSTER_ZERO_CA:0:3}"
kubectl auth can-i list pods --all-namespaces --as system:serviceaccount:kube-system:backstage-reader
kubectl auth can-i delete pods --all-namespaces --as system:serviceaccount:kube-system:backstage-reader
```

Expected: prefixos não vazios; `yes` para list; `no` para delete. Rodar o script uma segunda vez não deve falhar (idempotente).

- [x] **Step 4: shellcheck**

```bash
docker run --rm --volume "${PWD}:/mnt" --workdir /mnt koalaman/shellcheck:stable scripts/cluster-zero/backstage-reader
```

- [x] **Step 5: Commit**

```bash
git add scripts/cluster-zero/backstage-reader
git commit --message "feat(#101): ServiceAccount read-only do Backstage no cluster-zero"
```

### Task 3: Backstage lê o cluster-zero

**Files:**
- Modify: `idp/app-config.yaml` (bloco `kubernetes:`, hoje só com um comentário)

- [x] **Step 1: Editar** — substituir o bloco `kubernetes:` por:

```yaml
kubernetes:
  # see https://backstage.io/docs/features/kubernetes/configuration for kubernetes configuration options
  # Local k3d from scripts/cluster-zero. Credentials: eval "$(scripts/cluster-zero/backstage-reader)"
  serviceLocatorMethod:
    type: multiTenant
  clusterLocatorMethods:
    - type: config
      clusters:
        - name: cluster-zero
          url: https://127.0.0.1:6550
          authProvider: serviceAccount
          serviceAccountToken: ${K8S_CLUSTER_ZERO_TOKEN}
          caData: ${K8S_CLUSTER_ZERO_CA}
```

- [x] **Step 2: Prova com uma entidade existente** — anotar temporariamente o exemplo `example-website` e criar um pod com a mesma label (desfeito no Step 4):

Em `idp/examples/entities.yaml`, no `Component` `example-website`, acrescentar em `metadata`:

```yaml
  annotations:
    backstage.io/kubernetes-id: example-website
```

```bash
kubectl create namespace k8s-probe
kubectl --namespace k8s-probe run example-website --image=nginx:stable --labels=backstage.io/kubernetes-id=example-website
```

- [x] **Step 3: Verificar na UI**

```bash
eval "$(scripts/cluster-zero/backstage-reader)"
cd idp && yarn start
```

Login guest → catalog → `example-website` → aba **Kubernetes**: cluster `cluster-zero`, pod `example-website` Running. Log do backend sem erros `kubernetes` de TLS/401.

- [x] **Step 4: Desfazer a prova**

```bash
git checkout idp/examples/entities.yaml
kubectl delete namespace k8s-probe
```

- [x] **Step 5: Commit**

```bash
git add idp/app-config.yaml
git commit --message "feat(#101): Backstage lê o cluster-zero pelo plugin kubernetes"
```

- [x] **Step 6: Doc** — em `docs/idp/CLAUDE.md`, tabela da seção `## Scripts`, acrescentar duas linhas após `scripts/cluster-zero/verify`:

```markdown
| `scripts/cluster-zero/install-foundry-appset` | Applies the `foundry-apps` ApplicationSet: one ArgoCD `Application` per `apps/*` directory of `wasp-foundry/gitops` |
| `scripts/cluster-zero/backstage-reader` | Creates a read-only ServiceAccount and prints `K8S_CLUSTER_ZERO_TOKEN`/`K8S_CLUSTER_ZERO_CA` for the Backstage kubernetes plugin — `eval "$(scripts/cluster-zero/backstage-reader)"` before `yarn start` |
```

```bash
git add docs/idp/CLAUDE.md
git commit --message "docs(#101): scripts foundry do cluster-zero"
```
