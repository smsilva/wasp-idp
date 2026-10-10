# Base deck

- Deck original de 2 slides (não publicado); o conteúdo está reproduzido neste arquivo.
- Slide 1: mapa dos 5 planes e suas categorias. Fonte declarada nas notas: <https://platformengineering.org/platform-tooling>.
- Slide 2: arquitetura de referência — uma ou mais tools por categoria, majoritariamente Azure.

## Fonte dos planes

A página <https://platformengineering.org/platform-tooling> lista os 5 planes — Developer Control, Integration & Delivery, Resource, Observability, Security — como **camadas paralelas** de um landscape de ferramentas, não como sequência. Qualquer slide que afirme "uma plataforma se organiza em cinco planes" cita essa fonte. A ordem em que a apresentação percorre os planes (a jornada de um pedido) é **escolha narrativa nossa** e deve ser dita como tal.

## Arquitetura de referência (slide 2)

| Plane | Categoria | Tool |
|---|---|---|
| Developer Control | IDE / CDE | VS Code |
| Developer Control | Copilots / Agents / LLM | Claude Code |
| Developer Control | Portal | Backstage |
| Integration & Delivery | Version Control | GitHub, Bitbucket |
| Integration & Delivery | Registry | Azure Container Registry |
| Integration & Delivery | Platform Orchestrator | Kratix |
| Integration & Delivery | Services / App Spec | Score |
| Integration & Delivery | CI / CD pipeline | GitHub Actions (CI), Argo CD (CD) |
| Integration & Delivery | Platform / IaC | Crossplane, Terraform |
| Resource | Compute | Azure Kubernetes Service |
| Resource | Data | Azure SQL |
| Resource | Networking | Azure DNS |
| Resource | Services | Azure Service Bus |
| Observability | Monitoring & Logging | Azure Monitor |
| Observability | Observability | Prometheus, Grafana |
| Observability | FinOps | Kubecost |
| Observability | Incident Management | PagerDuty |
| Security | Code Analysis | SonarQube |
| Security | Secrets | Azure Key Vault |
| Security | ID Management | Auth0 |
| Security | Policy Control | Kyverno, Azure Policy |
| Security | Network Security | Cilium |
| Security | Security Suites | Prisma Cloud, Snyk |

A mesma tabela existe como entidades Backstage em `catalog/idp.yaml` (ver `audience-model.md`).
