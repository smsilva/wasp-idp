# SSO with Dex

Conceitos para os slides de identidade (Security Plane). Fonte: quatro ADRs **propostos** (2026-10-04) de uma PoC de referência do time, escritos com apoio do claude.ai — não são decisões deste repo. Nomes de org, CLI e cluster foram neutralizados aqui.

## Problema

- Vários clients precisam da **mesma identidade e dos mesmos grupos**: portal (Backstage), CLI da plataforma, Argo CD e o RBAC dos clusters (EKS via OIDC identity provider). O LiteLLM entra também.
- GitHub OAuth não é OIDC para usuários: o EKS não aceita o GitHub direto. Login direto no GitHub pelo portal resolve só o portal.

## Decisão proposta: Dex como único OIDC issuer

- Um **Dex standalone** emite os tokens de toda a plataforma; a fonte de identidade é um *connector* (na PoC de referência, o GitHub da org, com os teams virando o claim `groups`).
- Um client estático por consumidor: portal (confidential), CLI (public, com PKCE e redirect em localhost), Argo CD (`oidc.config` apontando para o Dex), clusters (EKS registra o Dex como OIDC identity provider, `groupsClaim: groups`).
- **Trocar a fonte é trocar o connector** (GitHub → Google Workspace, Entra ID, LDAP, SAML); portal, CLI, Argo CD e clusters não mudam. Ressalva: Google Workspace não manda grupos no login OIDC — exige service account e Admin SDK.
- **Trocar o issuer depois é caro** (todos os clients e clusters): o IdP de produção deve ser escolhido antes de multiplicar clusters.

Alternativas descartadas no ADR:

- Login direto no GitHub pelo portal: não cobre CLI nem clusters.
- Amazon Cognito: não federa o GitHub; grupos externos só com Lambda de Pre Token Generation; issuer amarrado à AWS mesmo com parte da infra no Azure.
- Dex embutido do Argo CD: acoplado à config e ao lifecycle do Argo CD.

## Quem decide o quê

- **No portal, o ownership vem do catálogo:** o login casa com a entidade `User`, cujo `memberOf` vem dos teams ingeridos do GitHub. Quem não existe no catálogo não entra.
- **No Kubernetes, quem decide é o claim `groups` do token** — o API server não conhece o catálogo.
- Catálogo e claim divergem só durante o intervalo de sync. Aceito.
- `User`/`Group` no catálogo é o contrato; a origem (GitHub Teams na PoC) é só um adapter trocável.

## Identidade e auditoria

- **Chave imutável = ID numérico do GitHub**; o login é rótulo (pode ser renomeado e reaproveitado por outra pessoa).
- A cada login, o par `login ↔ user_id` vai para um audit sink.
- O catálogo **não** é trilha de auditoria. A trilha vive no Git (todo Environment/claim/deploy é commit ou PR), no auditor do Backstage, nos audit logs do API server, nos events do Argo CD e do Crossplane — tudo num sink central no Observability Plane.

## Onde o Dex roda

- No cluster de plataforma (hub), como **componente do Security Plane, não acessório do portal**: namespace e Argo CD Application próprios, secrets via External Secrets, NetworkPolicy, `storage: kubernetes` (chaves sobrevivem a restart), duas réplicas.
- **Issuer estável e independente de onde o Dex roda** (`https://id.<base-domain>`): mover o Dex é trocar o destino da Application.
- **Break-glass:** todo cluster, inclusive o hub, mantém acesso administrativo via IAM (EKS access entries). O acesso ao cluster que roda o Dex nunca depende do Dex.
- Se o hub cair, nenhum token novo é emitido; os clusters seguem rodando, e o break-glass cobre o intervalo.
- O EKS exige issuer publicamente acessível (discovery + JWKS).

## Relação com este repo

- A arquitetura de referência do deck base tem Auth0 em ID Management. Nesta plataforma, a avaliação com Dex foi substituída por **Keycloak como broker de identidade** (ADR 0021, em proposta): o Google autentica, o Keycloak guarda usuários e grupos (`platform-admins`, `platform-users`) e emite o JWT que a Platform API valida.
- **Por que não Dex:** com conta Google pessoal (fora do Workspace) o Google não fornece grupos, e o Dex não guarda usuários nem grupos — a claim `groups` não teria origem. O Keycloak guarda os grupos e suporta Authorization Code + PKCE e Device Authorization Grant nativamente, então o Dex viraria um segundo broker sem função.
- Os princípios deste arquivo continuam valendo com o Keycloak no lugar do Dex: um único issuer, a origem da identidade como conector trocável, break-glass fora do SSO e identidade imutável como chave.
