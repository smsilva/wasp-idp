# Use the environment

O `--wait` grava o kubeconfig. Para um ambiente criado sem ele, `platform environment get` faz o mesmo:

```bash
platform environment get greetings-test
```

```
greetings-test: ready
  vcluster running in namespace env-greetings-test, API on 127.0.0.1:7100
  kubectl --kubeconfig ~/.config/platform/environments/greetings-test.kubeconfig get nodes
```

```bash
export KUBECONFIG=~/.config/platform/environments/greetings-test.kubeconfig
kubectl get nodes
kubectl create deployment web --image nginx:alpine
```

```
NAME                          STATUS   ROLES    AGE   VERSION
k3d-platform-local-server-0   Ready    <none>   17s   v1.36.0
```

O nó que aparece é o do `platform-local`: o vcluster tem API, etcd e controllers próprios, e os pods rodam no cluster de fora, no namespace `env-greetings-test`. Cada ambiente ganha uma porta da faixa `7100`–`7119`, mapeada pelo `init` em `127.0.0.1`.

O kubeconfig não guarda credencial (ADR 0028). A cada comando, o kubectl chama `platform environment credential greetings-test`, e a Platform API confere se você ainda tem acesso ao ambiente e devolve um token de 10 minutos. Por isso a CLI precisa estar instalada e logada na máquina onde o kubectl roda; o `get` grava no kubeconfig o caminho da própria CLI. Dentro do vcluster, você é a ServiceAccount `platform-identities/<sub>`, com `cluster-admin`:

```bash
kubectl auth whoami
```

```
ATTRIBUTE   VALUE
Username    system:serviceaccount:platform-identities:6f1c9a8e-2b1d-4c3e-9f00-123456789abc
Groups      [system:serviceaccounts system:serviceaccounts:platform-identities system:authenticated]
```

Quem está em `platform-admins` também pode gravar o kubeconfig de administrador do vcluster, com certificado e sem passar pela API, em `~/.config/platform/environments/<nome>-admin.kubeconfig`:

```bash
platform environment get greetings-test --admin
```
