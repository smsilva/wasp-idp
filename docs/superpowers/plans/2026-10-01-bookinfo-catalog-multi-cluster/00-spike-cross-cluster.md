# Cross-Cluster ArgoCD Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Responder o risco 1 do spec — com que endereço e com que configuração de TLS o ArgoCD de um k3d alcança a API de outro k3d na mesma rede Docker.

**Architecture:** Dois clusters descartáveis (`spike-hub`, `spike-target`) na rede `k3d-idp`, ArgoCD no hub, um Secret de cluster apontando para o target, uma Application de exemplo público. Tudo apagado no fim; o único artefato versionado é o resultado registrado no spec.

**Tech Stack:** k3d, ArgoCD (chart `argo/argo-cd` 10.2.1), kubectl.

**Spec:** `docs/superpowers/specs/2026-10-01-bookinfo-catalog-multi-cluster-design.md` — "Riscos a validar primeiro", item 1; "Componentes › Clusters".

## Global Constraints

- Rede Docker: `k3d-idp`.
- Endereço candidato do target: `https://k3d-<nome>-server-0:6443`; alternativa: `https://k3d-<nome>-serverlb:6443`.
- Preferência: `tlsClientConfig.insecure: false` com `caData`. `insecure: true` só como fallback, registrado depois em known-broken.
- Não tocar no `idp-cluster-zero` existente nem nas portas `6550`–`6552`, `9080`–`9082`: o spike usa `6560`/`6561` e nenhuma porta de app.

## Review Focus

- O target recriado (mesmo nome) muda a CA: o Secret de cluster precisa ser regravado — registrar no resultado se o ArgoCD reporta erro claro de TLS nesse caso.
- Contexto corrente do kubectl depois do spike: deve voltar a um contexto existente, não ficar apontando para cluster apagado.

---

### Task 1: Clusters descartáveis e ArgoCD no hub

**Files:** nenhum no repo.

- [ ] **Step 1: Rede e clusters**

```bash
docker network inspect k3d-idp > /dev/null 2>&1 || docker network create k3d-idp
k3d cluster create spike-target --servers 1 --api-port 6561 --network k3d-idp --k3s-arg '--disable=traefik@server:*' --wait --timeout 300s
k3d cluster create spike-hub --servers 1 --api-port 6560 --network k3d-idp --k3s-arg '--disable=traefik@server:*' --wait --timeout 300s
docker network inspect k3d-idp --format '{{range .Containers}}{{.Name}} {{end}}'
```

Expected: os containers `k3d-spike-target-server-0`, `k3d-spike-target-serverlb`, `k3d-spike-hub-server-0`, `k3d-spike-hub-serverlb` na rede.

- [ ] **Step 2: ArgoCD no hub**

```bash
helm upgrade --install --kube-context k3d-spike-hub --namespace argocd --create-namespace argocd argo/argo-cd --version 10.2.1 --wait > /dev/null
kubectl --context k3d-spike-hub --namespace argocd get deploy
```

Expected: deployments `Available`.

### Task 2: Registrar o target e sincronizar uma Application

- [ ] **Step 1: ServiceAccount no target**

```bash
kubectl --context k3d-spike-target apply --filename - <<'EOF'
apiVersion: v1
kind: ServiceAccount
metadata:
  name: argocd-manager
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: argocd-manager
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: argocd-manager
    namespace: kube-system
---
apiVersion: v1
kind: Secret
metadata:
  name: argocd-manager-token
  namespace: kube-system
  annotations:
    kubernetes.io/service-account.name: argocd-manager
type: kubernetes.io/service-account-token
EOF
kubectl --context k3d-spike-target --namespace kube-system wait --for jsonpath='{.data.token}' secret/argocd-manager-token --timeout=60s
token="$(kubectl --context k3d-spike-target --namespace kube-system get secret argocd-manager-token --output jsonpath='{.data.token}' | base64 --decode)"
ca="$(kubectl --context k3d-spike-target --namespace kube-system get secret argocd-manager-token --output jsonpath='{.data.ca\.crt}')"
echo "${token:0:3} ${ca:0:3}"
```

Expected: prefixos `eyJ` e `LS0`.

- [ ] **Step 2: SAN do certificado do target** (antes de testar pelo ArgoCD)

```bash
docker exec k3d-spike-target-server-0 sh -c 'cat /var/lib/rancher/k3s/server/tls/serving-kube-apiserver.crt' \
  | openssl x509 -noout -ext subjectAltName
```

Registrar a lista de SANs. Expected (hipótese): contém `k3d-spike-target-server-0` e/ou `k3d-spike-target-serverlb`.

- [ ] **Step 3: Secret de cluster com TLS verificado** — usar o primeiro endereço que o Step 2 mostrou no SAN (`server-0` se presente, senão `serverlb`):

```bash
server="https://k3d-spike-target-server-0:6443"
kubectl --context k3d-spike-hub apply --filename - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: cluster-spike-target
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: cluster
    env: spike
type: Opaque
stringData:
  name: spike-target
  server: ${server}
  config: |
    {"bearerToken": "${token}", "tlsClientConfig": {"insecure": false, "caData": "${ca}"}}
EOF
```

- [ ] **Step 4: Application de prova**

```bash
kubectl --context k3d-spike-hub apply --filename - <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: guestbook
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/argoproj/argocd-example-apps.git
    targetRevision: HEAD
    path: guestbook
  destination:
    server: ${server}
    namespace: guestbook
  syncPolicy:
    automated: {}
    syncOptions:
      - CreateNamespace=true
EOF
kubectl --context k3d-spike-hub --namespace argocd wait application/guestbook --for jsonpath='{.status.sync.status}'=Synced --timeout=240s
kubectl --context k3d-spike-target --namespace guestbook get deploy
```

Expected: `Synced`; deployment `guestbook-ui` no target. Se falhar, ler `kubectl --context k3d-spike-hub --namespace argocd get application guestbook --output jsonpath='{.status.conditions}'`:
- erro `x509: certificate is valid for ..., not k3d-spike-target-server-0` → trocar `server` para um nome que esteja no SAN do Step 2 e reaplicar Steps 3–4;
- nenhum nome do SAN funciona → `"insecure": true` sem `caData` e reaplicar (fallback do spec).

### Task 3: Resultado e limpeza

- [ ] **Step 1: Limpar**

```bash
k3d cluster delete spike-hub spike-target
kubectl config get-contexts --output name
kubectl config use-context k3d-idp-cluster-zero 2> /dev/null || true
```

A rede `k3d-idp` fica (é a rede definitiva do plano 01).

- [ ] **Step 2: Registrar no spec** — em `docs/superpowers/specs/2026-10-01-bookinfo-catalog-multi-cluster-design.md`, "Riscos a validar primeiro", item 1, acrescentar ao fim: `— **resultado (AAAA-MM-DD):** <endereço que funcionou>, <insecure: false com caData | insecure: true>; SAN do k3s: <lista>.` Se o endereço não for `k3d-<nome>-server-0`, corrigir também a linha do `register-clusters` em "Componentes › Clusters".

```bash
git add docs/superpowers/specs/2026-10-01-bookinfo-catalog-multi-cluster-design.md
git commit --message "docs(#105): resultado do spike de ArgoCD entre clusters k3d"
```

**Interfaces:**
- Produces: o valor de `server` (formato `https://k3d-<nome>-<server-0|serverlb>:6443`) e o modo TLS que o plano 01, Task 3, usa em `register-clusters`.
