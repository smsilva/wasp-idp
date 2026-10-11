# Provider workload

Aplica cada `WorkloadRevision` no vcluster do seu `Environment` e mantém a `WorkloadInstance` ([ADR 0033](../../../docs/adr/0033-workload-spec-and-workload-instance.md), #292). Funciona com qualquer `Environment` `Ready` que tenha `status.kubeconfigData`, sem depender do `local_vcluster`.

Roda **dentro do cluster**, como Deployment `workload-provider` em `platform-system`, instalado pelo `platform init --target local`.

## Reconciliação

- A cada passada, lista revisões e instâncias. Por instância (`<environment>.<instance>`), só a revisão mais nova conta: uma mais antiga ainda aberta fecha como `Superseded`.
- Revisão aberta (`Ready` ausente ou `Unknown`): lê o `Environment` (sem `Ready` vira `EnvironmentNotReady`, que segue aberta) e a `Version` (`<component>.<version>`). Gera Namespace `apps`, Deployment e Service a partir do Score (`manifests.py`), aplica com server-side apply (field manager `platform-workload`) e acompanha o rollout. Fecha como `Succeeded` ou `RolloutFailed` (o Deployment sai com `progressDeadlineSeconds: 120`) e cria ou atualiza a instância.
- Falhas finais, sem tocar no vcluster: `SpecNotIndexed`, `ResourcesNotSupported` (até a #263), `UnsupportedSpec`. `ApplyFailed` quando o vcluster recusa ou não responde.
- Revisão `Succeeded` mais nova: atualiza réplicas e `Ready` da instância (`Available`, `Progressing`, `Degraded`) só quando mudam.
- Watch das revisões com timeout de 5 s enquanto há revisão aberta (`--poll-seconds`) e de 30 s no resto do tempo (`--resync-seconds`); uma revisão nova interrompe a espera.
- Revisões e instância têm owner reference para o `Environment`: somem com ele.

## Acesso ao vcluster

Usa o kubeconfig admin de `Environment.status.kubeconfigData`, trocando o servidor (que aponta para `127.0.0.1`, para o host) por `https://vcluster.env-{name}` (o Service do chart, ClusterIP na 443, `--vcluster-server`), o mesmo endereço que a Platform API usa em `credentials.py`. Um client por ambiente fica em cache enquanto o kubeconfig não muda.

## Permissões

Role em `platform-system`: lê revisões e escreve o status delas; cria, apaga e escreve o status das instâncias; lê `environments` e `versions.catalog`. Nada fora do namespace: o acesso ao vcluster vem do kubeconfig.

## Testes

```bash
uv sync
uv run pytest
```
