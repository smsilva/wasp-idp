# Use the environment

!!! step "Gravar o kubeconfig"

    O `get` de um ambiente pronto grava o kubeconfig em `~/.config/platform/environments/`:

    ```bash
    platform environment get greetings-test

    kubeconfig=~/.config/platform/environments/greetings-test.kubeconfig
    ```

!!! step "Usar o cluster"

    ```bash
    kubectl get nodes \
      --kubeconfig "${kubeconfig}"

    kubectl create deployment web \
      --kubeconfig "${kubeconfig}" \
      --image nginx:alpine

    kubectl auth whoami \
      --kubeconfig "${kubeconfig}"
    ```

O kubeconfig chama `platform environment credential greetings-test` a cada comando. O `auth whoami` mostra a **sua identidade** no vcluster: `system:serviceaccount:platform-identities:<sub>`.

Como admin, grave também o **kubeconfig de administrador** do vcluster:

```bash
platform environment get greetings-test --admin
```
