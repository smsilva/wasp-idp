# Provider local de Environment (k3d)

Atende a capacidade `Environment` no target local: cada `Environment` do namespace `platform-system` no `platform-local` vira um cluster k3d `env-<nome>`.

Roda **no host**, não no cluster, porque precisa de Docker para criar clusters k3d. Iniciado em foreground por:

```bash
platform provider run --target local
```

## Reconciliação

- Adiciona o finalizer `platform.wasp.silvios.me/local-k3d`.
- Cria o k3d `env-<nome>` com a API numa porta livre em `127.0.0.1`, sem alterar o kubeconfig default, e grava o kubeconfig em `~/.config/platform/environments/<nome>.kubeconfig`.
- Grava `status.conditions` (`Ready=True`, `reason=ClusterReady`) e `status.kubeconfig`. Falhas viram `Ready=False, reason=ProvisioningFailed` com a mensagem.
- No delete, remove o cluster, o kubeconfig e o finalizer.
- Quando `spec.expiresAt` passa, apaga o `Environment`. A expiração é checada numa passada completa a cada `--resync-seconds` (30 s por padrão), além do watch.

Sem o provider rodando, os pedidos ficam em `NoProviderForCapability`; ao subir, ele converge tudo que estiver pendente.

## Testes

```bash
cd platform/providers/local_k3d
uv sync
uv run pytest
```
