# One provisioning method for cloud Environments (Crossplane); defer Kratix

**Status:** Aceito (2026-10-11)

## Contexto

A #254 liga o `Environment` a uma `CloudAccount` (ADR 0029) e deixou uma questão em aberto: o `Environment` numa conta pode ter mais de um método de provisionamento (Crossplane por padrão, OpenTofu como alternativa), como nas Promises do [Kratix](https://kratix.io/)? A própria #254 pede um ADR antes de implementar o método.

O spike da #207 instalou o Kratix no `platform-local` com uma Promise `cloud-environment` cuja API é um CRD da plataforma (`spec.cloudAccount`, `spec.method`, `spec.region`) e um pipeline que gera, por método, um `ProviderConfig` e uma `VPC` do Crossplane ou um `Terraform` do tofu-controller. Não houve chamada à AWS: o teste parou no que o Kratix entrega a cada destino. O resultado está na seção 3 de [`docs/superpowers/specs/2026-10-11-adopt-or-build-spike.md`](../superpowers/specs/2026-10-11-adopt-or-build-spike.md). Os fatos que decidem:

- **A fachada é boa:** a API da Promise é um CRD nosso, então o cliente não vê o Kratix. Mas as conditions do Kratix (`ConfigureWorkflowCompleted`, `Reconciled`, `WorksSucceeded`) se misturam às do `Environment` e dizem que os manifests foram entregues, não que a infraestrutura está pronta.
- **A escolha de método é pegajosa de um jeito perigoso:** trocar `spec.method` não move o pedido. A `WorkPlacement` fica `Misplaced` no destino antigo, e a saída do método novo é escrita nesse destino. Com Flux e `prune`, isso apagaria a VPC do Crossplane e entregaria um `Terraform` onde não há tofu-controller.
- **O Kratix não detecta drift na nuvem:** ele só reexecuta os pipelines (a cada 10 h, por padrão). O drift volta por um `HealthRecord` gravado por outra peça.
- **Custo:** três peças a operar (Kratix, state store, Flux ou ArgoCD em cada destino), distribuição só por uma release rolante `latest` (última tag semver de 2024) e governança fora da CNCF.

## Decisão

**Um `Environment` numa `CloudAccount` tem um método de provisionamento só, o Crossplane, implementado como provider da plataforma; o Kratix fica adiado.**

- **Seleção por provider, não por pipeline:** segue o padrão que a plataforma já usa (`local_vcluster`, `aws_account`). Sem conta, o `Environment` vai para o `local_vcluster`; com conta, para o provider de nuvem. Esse provider escreve os managed resources do Crossplane e o `ProviderConfig` gerado da `CloudAccount` (ADR 0029), e traduz o estado deles nas conditions do `Environment`.
- **O Crossplane é o método porque reconcilia o drift sozinho**, com o estado na kube API, e porque já é o que o EKS usa (`aws/eks/providers/provider-config-wasp-nonprod.yaml`).
- **Se um segundo método for necessário:**
  - entra como outro provider, selecionado por um campo do `Environment`;
  - o campo é imutável depois da criação, e mudar de método é uma migração explícita (novo `Environment`), nunca uma edição;
  - o OpenTofu iria pelo tofu-controller, com state num backend que não exige segredo na `CloudAccount`;
  - o drift detectado pelo `plan` periódico vira a condition `Drifted` no `Environment`, no mesmo papel do `HealthRecord` do Kratix.

## Quando revisitar o Kratix

Quando a plataforma tiver vários métodos ou vários tipos de recurso com pipelines próprios, mantidos por times diferentes, e entrega GitOps por destino já existir por outro motivo. Aí o state store e o Flux deixam de ser custo só do Kratix, e a Promise com o CRD nosso como API é o modelo a copiar ou adotar.

## Consequências

- A #254 implementa só o provider de Crossplane. O ADR 0029 continua valendo: o `ProviderConfig` é gerado da `CloudAccount`.
- O `Environment` não ganha `spec.method` agora. Ele entra junto com o segundo método, se houver, e já nasce imutável.
- O contrato do `Environment` para a CLI e a API (conditions `Ready` e reasons, ADR 0022) não depende do método.
- O Crossplane passa a ser exigido no target que provisiona em nuvem. No `platform-local`, ele só é instalado quando um `Environment` com conta for testado.
