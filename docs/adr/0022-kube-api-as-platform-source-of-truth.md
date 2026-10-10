# Kubernetes API as the platform source of truth

**Status:** Aceito (2026-10-10)

## Contexto

O domínio da plataforma é estado desejado que converge de forma assíncrona:
- ambientes, inclusive efêmeros com expiração;
- releases de uma versão de aplicação num ambiente;
- recursos de infra que atendem às necessidades declaradas no Score, em três modos: **provision** (recurso dedicado), **compose** (algo dentro de um recurso compartilhado existente) e **bind** (só conectar a algo que já existe).

Um pedido pode chegar antes de existir quem o atenda, e precisa ficar registrado até um provider reconciliar.

Guardar esse estado em tabelas próprias significaria reimplementar o que o API server do Kubernetes já oferece:
- watch;
- concorrência otimista (`resourceVersion`);
- separação `spec`/`status` com `conditions`;
- finalizers e owner references para limpeza em cascata;
- RBAC e validação por schema OpenAPI.

A plataforma já é feita de controllers (Crossplane, ArgoCD), e o resolvedor dos três modos foi pensado como controller.

Três restrições moldam a decisão:

- **O etcd não é banco de consulta.** Ele não tem joins nem agregações e limita cada objeto a ~1,5 MB. O portal precisa de agregados como "300 instâncias, 5 com drift".
- **Em clusters gerenciados (EKS, AKS) não há acesso ao etcd**, então backup de etcd não é opção.
- **Events do Kubernetes expiram** (~1h) e não servem como auditoria.

## Decisão

**CRDs no cluster de control plane da plataforma são a fonte da verdade do estado desejado; a Platform API é uma fachada sobre eles, e o Postgres guarda o journal dos pedidos e uma projeção para leitura.**

- **CRDs** no grupo `platform.wasp.silvios.me`:
  - `Environment`;
  - `Release`, nome escolhido para não colidir com o `Deployment` do Kubernetes;
  - `ResourceRequest`, um por recurso do Score, com o modo resolvido no `status`;
  - `BindingPolicy`, o default de modo por ambiente;
  - `ExternalResource`, alvo do modo `bind`.

  No perfil local, o cluster de control plane é o k3d criado pelo `platform init`.
- **Escrita:** a Platform API valida, autoriza e aplica os CRDs direto na kube API, por trás de uma interface `StateWriter`. A implementação inicial é `KubeApplyWriter`; um `GitCommitWriter` (GitOps) ou outro mecanismo pode substituí-la sem mudar a API.
- **Journal:** cada pedido aceito é gravado numa tabela append-only no Postgres, com spec completo, autor e horário, *antes* de ser aplicado, e marcado como aplicado depois. Um reconciliador reaplica intenções pendentes. O journal é a auditoria e também o caminho de recuperação: o replay recria os CRDs se o cluster de control plane for perdido.
- **Leitura:** um projector com informers grava no Postgres o estado dos CRDs e o drift dos spokes. Listas e agregados vêm dessa projeção; o detalhe de um objeto pode vir direto do CR.
- **Pedido sem provider** é uma condition padrão (`Ready=False`, `reason=NoProviderForCapability`), não um status próprio. Quando o provider entra, o controller reconcilia.
- **Fluxos com passos e fim ficam fora dos controllers.** Build, promoção com aprovação humana e restore rodam em workflow (Argo Workflows ou GitHub Actions), disparados pela API. O resultado volta como dado: uma versão registrada, um `ExternalResource` ou um `Release`.

## Consequências

- O Postgres tem dois papéis com exigências diferentes. O journal é durável e precisa de backup; a projeção é descartável e reconstruível pelo projector.
- A recuperação não depende de backup de etcd. Velero, que faz backup de objetos da API e funciona em cluster gerenciado, fica como segunda linha.
- O cluster de control plane vira peça crítica e não roda workload de aplicação.
- Clientes (CLI, Backstage, agentes) nunca acoplam ao formato dos CRDs, porque falam só com a Platform API.
- A adoção futura de GitOps para os pedidos dos times fica confinada ao `StateWriter`.
- Fica em aberto se os `Release` de produção devem ser espelhados num repositório para ter histórico versionado e revisão por PR.
