# Proof of concept (this repo)

Exemplos concretos que a apresentação pode usar, todos verificáveis neste repo. A arquitetura de referência do deck base é Azure; a PoC roda na AWS.

- **Environment como claim:** 1 claim `Environment` vira um cluster EKS inteiro (~28-30 min) com rede, DNS numa sub-zona delegada no Route 53, certificado, Gateway, identidade e GitOps (Argo CD). Abstrações (XRDs e compositions) em `aws/eks/resources/`; tempos por etapa em `aws/eks/README.md` (o control plane do EKS domina, ~12-15 min).
- **Gate em ação irreversível:** destruir o ambiente exige `--yes-destroy` (`aws/eks/scripts/teardown`); `make clean` recusa sem `CONFIRM=1`.
- **Hub-and-spoke:** a topologia AWS (conta `network` com o hub, células por região, ingress centralizado) está nos ADRs em `docs/adr/` e em `aws/docs/`.
- **Decisão de produto:** o `Environment` é "a entrada do catálogo do IDP", consumida por diferentes clients (Backstage, CLI, agente).
- **Portal:** Backstage em `idp/` (roda local), com template `python-service` que cria repo e PR no repo GitOps central, catálogo descoberto da org GitHub (ADR 0020) e exemplos de catálogo completos (Domain `communication`, Domain `bookstore`). Deploy em dois ambientes (`development`, `production`) pelo Argo CD central (ADR 0019).
- **Mapa para os planes:** Claude Code e Backstage = Developer Control; Crossplane = IaC; Argo CD = Delivery; Route 53 = Networking; Secrets Manager + ESO = Secrets.
- **Enquadramento na apresentação:** o MVP 1 da plataforma é este caminho — um control plane (hoje k3d local) roda Crossplane e Argo CD e provisiona `Environment`s na AWS.
