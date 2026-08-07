# Multi-tenant Internal Developer Platform — Design

## Contexto

Hoje existe um PoC de Backstage single-instance em `idp/` (branch `dev`) com customizações de UI (tema, navegação, sign-in) e autenticação Google OAuth. Este design define como evoluir esse PoC para uma plataforma que atenda ~120 projetos (tipicamente um por cliente), cada um com necessidade de isolamento forte entre si.

Referências usadas na definição:
- `~/downloads/idp.pdf` — stack de ferramentas alvo (GitHub, GitHub Actions, ArgoCD, Crossplane, Azure, New Relic, Snyk, SonarCloud, AKV, Auth0/Azure Entra, RabbitMQ/Kafka, Istio, KEDA)
- `~/downloads/presentation.pdf` (Humanitec, Platform Engineering) — framework de referência de 4 planos (Developer Control, Integration & Delivery, Observability, Security, Resource)
- Repos locais existentes: `azure-subscription-foundation`, `azure-platform-foundation`, `azure-wasp-foundation`, `wasp-gitops`

## Por quê

**Problema:** Backstage sozinho não resolve visibilidade multi-cliente com isolamento de segurança. É necessário decidir como uma única tecnologia de portal atende dezenas de projetos sem vazamento de informação entre eles, e como o provisionamento de infraestrutura por projeto é automatizado de ponta a ponta.

**Requisito não negociável:** isolamento entre projetos é uma questão de **segurança**, não apenas de organização/UX. Times de um projeto não podem sequer saber da existência de outro.

**Alternativa rejeitada:** RBAC nativo do Backstage numa instância única. Seria mais barato de operar, mas o risco de vazamento por erro de configuração de permissão é inaceitável dado o requisito de segurança — e auditar isolamento real dentro de uma instância compartilhada é estruturalmente mais difícil do que auditar isolamento entre instâncias/clusters separados.

**Abordagem escolhida:** uma instância Backstage por projeto, cada uma isolada em seu próprio contexto de credenciais e catálogo, com todo o provisionamento (infraestrutura, instância, catálogo) dirigido por GitOps.

## Perfis de usuário

| Perfil | Necessidade |
|---|---|
| Desenvolvedor | Acesso aos serviços do seu projeto; visibilidade de serviços de outros times **dentro do mesmo projeto**; nenhuma visibilidade de outros projetos |
| Gestor | Métricas agregadas por time e por projeto (status de deploy, qualidade, incidentes) |
| Platform Engineer | Responsável pela entrega de infraestrutura (via Crossplane/GitOps) e pela manutenção das instâncias Backstage. Papel operacional da plataforma, não do produto do cliente |

## Escala e cadência

- ~120 projetos (tipicamente um por cliente), volume oscila para mais e para menos ao longo do tempo
- Crescimento não é acelerado, mas o número já descarta qualquer processo manual de setup por projeto — a plataforma precisa se auto-provisionar

## Arquitetura

### Modelo de clusters

```
Cluster regional de plataforma (1 por região)
├── ArgoCD (GitOps controller)
├── Crossplane (provisiona clusters de workload)
└── N instâncias Backstage (1 por projeto), isoladas por namespace

Clusters de workload (N por projeto × ambiente: dev/staging/prod)
└── Provisionados pelo Crossplane, sob demanda, via GitOps
```

O cluster regional de plataforma é multi-tenant apenas na camada de execução (namespaces); cada instância Backstage dentro dele tem seu próprio `app-config`, credenciais e fonte de catálogo — sem overlap de dados entre projetos.

### Bootstrap do cluster regional ("cluster zero")

GitOps pressupõe um cluster já existente para rodar o ArgoCD — por isso o cluster regional não pode nascer via GitOps. Ele é criado por Terraform dedicado, fora do ciclo GitOps:

```
azure-subscription-foundation   → bootstrap da subscrição (RG, AKV, tfstate storage)
azure-platform-foundation       → cria instâncias de plataforma por região (RG, Event Grid)
  └── [NOVO] módulo AKS regional → cluster que hospeda ArgoCD + Crossplane + instâncias Backstage
```

Após o Terraform aplicar o AKS regional e instalar ArgoCD, todo provisionamento subsequente (novos projetos, novos clusters de workload) passa a ser 100% GitOps.

### Onboarding de um novo projeto

1. Platform engineer commita um Kind (custom resource) no repo de bootstrap com o nome/parâmetros do novo projeto
2. ArgoCD ApplicationSet detecta o novo Kind e instala uma instância Backstage via Helm chart único e parametrizado, num namespace isolado do cluster regional
3. Configuração não-sensível vem do `values.yaml` do projeto (GitHub org, ArgoCD endpoint, New Relic account, etc.)
4. Credenciais sensíveis (tokens, secrets) vêm do AKV do projeto (já provisionado pelo `azure-wasp-foundation`) via External Secrets Operator — nunca tocam o repositório GitOps
5. O Software Template do Backstage gera automaticamente o `catalog-info.yaml` para novos serviços; repos existentes recebem o arquivo via script de bulk-registration
6. GitHub Discovery é habilitado automaticamente, escaneando apenas a org GitHub daquele projeto

```
GitOps repo (bootstrap)
└── Kind commit (novo projeto)
     └── ArgoCD ApplicationSet
          └── Helm install Backstage (namespace isolado)
               ├── values.yaml (config não-sensível)
               └── External Secrets ← AKV do projeto (credenciais)
```

### Repositórios GitOps: Platform Library vs. GitOps do projeto

Dois tipos de repositório com propósitos e permissões distintos:

**Platform Library** (central, mantido pelo platform team, **read-only** para instâncias Backstage de projeto)
- Crossplane Compositions e XRDs — os building blocks (cluster AKS, banco, fila, etc.)
- Helm charts da plataforma, versionados semanticamente e publicados
- Umbrella chart que instala um conjunto pré-selecionado de subcharts (modelo inspirado nos charts da New Relic: subcharts instaláveis isoladamente ou via umbrella)

**GitOps do projeto** (um por projeto, write restrito à instância Backstage daquele projeto)
- Contém apenas declarações de consumo: `HelmRelease`, Crossplane `Claims`, `values.yaml`
- Referencia versões publicadas do Platform Library — nunca modifica os building blocks
- Quando um platform engineer usa o Software Template "criar workload cluster" no Backstage, a ação resultante é um commit neste repo

Esse desenho resolve o problema de write access: cada instância Backstage só tem permissão de escrita no seu próprio repo GitOps de projeto, nunca no repo central ou no de outros projetos. Blast radius de uma instância comprometida fica limitado ao projeto correspondente.

### Catálogo do Backstage

- Fonte primária: GitHub Discovery restrito à org GitHub do projeto (isolamento nativo por escopo de credencial)
- Repos novos: `catalog-info.yaml` gerado automaticamente pelo Software Template de criação de serviço
- Repos existentes (ex: `azure-*-foundation`, `wasp-gitops`): migração via script de bulk-registration, usando nome do repo, linguagem e topics já existentes no GitHub como metadata inicial
- Extensível no futuro para outros provedores Git (ex: Bitbucket) através dos processors de discovery equivalentes do Backstage — não há lock-in em GitHub na arquitetura, apenas na integração inicial

### Visibilidade por plano (mapeamento stack → Backstage plugins)

| Plano | Ferramenta | Plugin |
|---|---|---|
| Developer Control | GitHub | `@roadiehq/backstage-plugin-github-insights` |
| Developer Control | GitHub Actions | `@backstage/plugin-github-actions` |
| Developer Control | Jira | `@roadiehq/backstage-plugin-jira` |
| Integration & Delivery | ArgoCD | `@roadiehq/backstage-plugin-argo-cd` |
| Integration & Delivery | Crossplane | custom plugin (gap identificado, sem solução pronta na comunidade) |
| Observability | New Relic | `@roadiehq/backstage-plugin-newrelic` |
| Observability | FinOps (custo Azure) | custom plugin |
| Security | Snyk | `@roadiehq/backstage-plugin-snyk` |
| Security | SonarCloud | `@backstage/plugin-sonarqube` |
| Security | Azure Key Vault (inventário) | custom plugin |
| Resource | AKS | `@backstage/plugin-kubernetes` |
| Resource | KEDA / Istio | custom plugin ou extensão do Kubernetes plugin |

## Fora de escopo deste design

- Implementação dos plugins customizados (Crossplane, FinOps, AKV inventory) — ficam como epics separados a priorizar depois da fundação
- Definição fina de RBAC dentro de uma instância (dev vs. gestor vs. platform engineer no mesmo projeto) — depende da fundação multi-instância estar operacional primeiro
- Suporte a Bitbucket — mencionado como direção futura, não implementado neste design
- Métricas agregadas cross-projeto para gestores que atendem múltiplos clientes (hoje cada instância é isolada; um dashboard agregado, se necessário, seria um serviço separado fora do Backstage)

## Riscos e pontos em aberto

- **Bulk-registration de catálogo** para os repos `azure-*-foundation` existentes ainda não tem script definido — depende de convenção de naming/topics a ser acordada com o time
- **Cluster zero** é o único ponto do sistema fora do ciclo GitOps — precisa de runbook claro e acesso restrito, já que não passa pelo mesmo controle de auditoria do resto
- **Repo GitOps por projeto** multiplica para ~120 repos — a criação desses repos precisa ser ela mesma automatizada (via Terraform `github_repository` provider ou GitHub API) como parte do onboarding, senão vira gargalo manual