# Environments

## 8. Criar um ambiente

```bash
time platform environment create greetings-test --profile ephemeral --expires 1h --wait
```

``` { .text .output title="saída" }
provisioning greetings-test (profile: ephemeral) …
  NoProviderForCapability
  Provisioning
✓ greetings-test ready

real    0m32s
```

!!! note
    O pedido começa em `NoProviderForCapability` e o provider `local_vcluster`, que roda dentro do `platform-local`, o assume em seguida. Não há segundo terminal.

## 9. O provider por dentro

```bash
kubectl --context k3d-platform-local --namespace platform-system logs deploy/local-vcluster-provider --tail 3
kubectl --context k3d-platform-local get namespaces | grep env-
```

``` { .text .output title="saída" }
INFO creating vcluster env-greetings-test on port 7100
INFO environment greetings-test ready
env-greetings-test   Active   40s
```

## 10. Usar o ambiente

```bash
platform environment get greetings-test
kubectl --kubeconfig ~/.config/platform/environments/greetings-test.kubeconfig get nodes
kubectl --kubeconfig ~/.config/platform/environments/greetings-test.kubeconfig create deployment web --image nginx:alpine
kubectl --kubeconfig ~/.config/platform/environments/greetings-test.kubeconfig auth whoami
```

O kubeconfig chama `platform environment credential greetings-test` a cada comando. O `auth whoami` mostra a sua identidade no vcluster: `system:serviceaccount:platform-identities:<sub>`.

Como admin, grave também o kubeconfig de administrador do vcluster:

```bash
platform environment get greetings-test --admin
```

## 11. Segundo ambiente, em paralelo

```bash
platform environment create demo --profile ephemeral --expires 1h --wait
platform environment get demo
platform environment list --output json
```

!!! note
    Cada ambiente ganha a próxima porta livre da faixa `7100`–`7119` (`demo` fica na `7101`).

## 12. Trilha de auditoria

```bash
kubectl --context k3d-platform-local --namespace platform-system \
  exec deploy/platform-api -- cat /var/lib/platform/journal.jsonl \
  | jq --compact-output 'select(.action) | {at, actor, action, name}'
```

``` { .json .output title="saída" }
{"at":"2026-10-10T20:37:30+00:00","actor":"2016b176-… (voce@example.com)","action":"create","name":"greetings-test"}
{"at":"2026-10-10T20:38:45+00:00","actor":"2016b176-… (voce@example.com)","action":"create","name":"demo"}
```
