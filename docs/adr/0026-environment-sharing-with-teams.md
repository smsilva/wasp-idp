# Environment sharing with teams: teams as Keycloak groups owned by the Platform API, sharedWith on the Environment

**Status:** Aceito (2026-10-11)

## Contexto

Hoje um `Environment` é de quem o criou. A API grava o `sub` do token na anotação `platform.wasp.silvios.me/owner` (#184), e só o dono ou `platform-admins` recebem o `kubeconfigData` e podem apagar o ambiente (#185). O pedido da #186 é compartilhar um ambiente com o meu time: outras pessoas do time recebem o kubeconfig e o veem na listagem.

Não existe time na identidade da plataforma. O realm `platform` (`platform/keycloak/realm-platform.yaml`) tem só `platform-admins` e `platform-users`, que chegam ao token na claim `groups`, sem path, e a API os lê em `Principal.groups`. Os times existem só como `Group` no Backstage (`idp/catalog/org.yaml`: `team-alpha`, `team-beta`, `team-platform`), sem ligação com o Keycloak.

Dois outros pontos esperam por times: o `owner` do catálogo é texto livre "até os grupos de time existirem no Keycloak" (ADR 0023), e a #218 define o dono de uma service account como um grupo. A escolha de onde os times moram vale para os três casos.

O repo é público, então a lista de membros (e-mails) não pode ficar em arquivo versionado. Com conta Google pessoal, o Google não fornece grupos (ADR 0021).

O acesso a um ambiente é o kubeconfig de administrador do vcluster, gerado pelo provider `local_vcluster` e devolvido em `status.kubeconfigData`. Compartilhar o ambiente, hoje, é compartilhar essa credencial.

## Decisão

**Um time é um grupo do Keycloak sob `/teams`, criado e mantido pela Platform API. Um `Environment` declara com quais times é compartilhado em `spec.sharedWith`, e os membros desses times o usam com o mesmo kubeconfig, até o vcluster aceitar o token do Keycloak.**

### Times

- **O time é o grupo do Keycloak `/teams/<nome>`.** Ele é a fonte da verdade do time e dos membros. Não há CRD de time: a membership precisa estar no Keycloak para chegar ao token, e um segundo registro só criaria divergência.
- **A Platform API é a dona dos times**, pela admin API do Keycloak, com um client confidencial próprio (`platform-api-admin`, service account com `manage-users` e `view-users` no realm). A #218 reaproveita esse client para criar os clients das service accounts.
- **Comandos (#231):** `platform team create|list|get|delete` e `platform team member add|remove|list`. Só `platform-admins` criam e apagam times e mudam membros. Delegar a gestão de membros a um papel de "dono do time" fica para quando houver mais de um admin.
- **Nomes:** a claim `groups` continua sem path, então o token traz `team-alpha`. A API recusa nomes de time que colidem com grupos da plataforma (`platform-admins`, `platform-users`) e valida o nome com `re.fullmatch`.
- **O realm import não apaga os times.** Os times nascem pela API, fora do arquivo do realm, e o `realm-import` fixa `IMPORT_MANAGED_GROUP: no-delete`, como já faz com os client scopes, em vez de depender do remote state do keycloak-config-cli. Os times de exemplo do perfil local nascem pelo `platform init`, também pela API, nunca no `realm-platform.yaml`.
- **Auditoria:** criar, apagar e mudar membros de um time são entradas próprias do journal.

### Compartilhamento

- **`spec.sharedWith: [<time>, ...]` no `Environment`.** Lista vazia ou ausente significa privado, que continua sendo o padrão. A lista cobre "o meu time" e "outros times" sem um campo de visibilidade à parte.
- **O dono continua sendo uma pessoa** (anotação `owner`, o `sub`). A API passa a gravar também `owner-name` (e-mail do token) para exibição. O `sub` continua sendo o que vale para autorização.
- **Quem compartilha:** o dono ou um `platform-admin`. O dono só compartilha com times dos quais é membro. Compartilhar com um time do qual o dono não faz parte é só para admins. Fluxo de aprovação fica fora.
- **O que o time pode:** ler o ambiente com o `kubeconfigData`. Apagar, compartilhar e descompartilhar continuam com o dono e os admins.
- **Regra de acesso:** `pode_usar = dono ∨ admin ∨ (groups do token ∩ spec.sharedWith ≠ ∅)`. Ela substitui `is_owner_or_admin` na leitura do kubeconfig. Delete e share continuam com `is_owner_or_admin`.
- **CLI:** `platform environment create x --share-with team-alpha` (repetível), `platform environment share x --team team-alpha` e `platform environment unshare x --team team-alpha`.
- **Listagem:** por padrão, `environment list` mostra os ambientes do usuário e os compartilhados com os times dele, com as colunas `OWNER` e `SHARED`. `--all` lista todos, sem kubeconfig. Para admins, o padrão já é todos.
- **Auditoria:** `share` e `unshare` são ações próprias do journal, com os times afetados.

### Kubeconfig

- **Fatia 1 (#232): um kubeconfig para todos.** Os membros dos times recebem o mesmo kubeconfig de admin do vcluster. Tirar alguém do time corta o acesso pela API, mas quem já baixou a credencial continua com ela até o ambiente ser recriado. O risco é aceito para ambientes locais e efêmeros.
- **Fatia 2 (#233): uma identidade por pessoa.** O API server do vcluster passa a aceitar o token do Keycloak (OIDC), com RBAC por grupo dentro do vcluster (cada time de `sharedWith` vira um binding de RBAC para o grupo). O kubeconfig entregue deixa de ter credencial estática e usa o plugin `kubectl oidc-login`. A revogação passa a vir do Keycloak.

## Consequências

- A Platform API passa a ter credencial de administração do realm. É o segundo segredo atrás dela, depois da chave do GitHub App (ADR 0025), e segue o mesmo `SecretStore`.
- O `owner` do catálogo (ADR 0023) e o dono das service accounts (#218) podem ser validados contra os times. A troca do texto livre por um time existente é uma mudança própria, fora desta decisão.
- `platform catalog import` pode criar times a partir dos `Group` de `idp/catalog/org.yaml`, sem membros. Hoje o import pula `Group`.
- Entrar ou sair de um time só vale no próximo token. A mudança aparece no máximo no fim do access token atual, ou já no `platform login` seguinte.
- A fatia 2 exige, no perfil local, um issuer alcançável de dentro do vcluster e com HTTPS, o que o Keycloak em `http://localhost:8180` não oferece hoje. A #233 resolve isso.
- O `scripts/demo/cli-smoke` precisa de dois usuários de teste no mesmo time para exercitar o compartilhamento.
