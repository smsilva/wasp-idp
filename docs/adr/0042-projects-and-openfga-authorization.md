# Projects and OpenFGA as the authorization decision point

**Status:** Proposto (2026-10-15)

## Contexto

Hoje cada recurso da plataforma é de uma pessoa. A API grava o `sub` do token na anotação `owner`, e o acesso é decidido por funções escritas à mão: `can_use` (dono ∨ `platform-admins` ∨ times do token ∩ `spec.sharedWith`, ADR 0026) e `is_owner_or_admin`, ambas em `platform/api/src/platform_api/environments.py`. `CloudAccount` repete o mesmo `sharedWith`, e `users_of` em `teams.py` lista os CRs um a um para saber quem usa um time. Na prática isso já é autorização por relação (ReBAC), só que repetida em cada recurso e sem herança.

O passo seguinte é o **projeto**: o usuário entra na plataforma, cria projetos e, dentro deles, tem ambientes e entidades de catálogo. Uma entidade de catálogo pode ser compartilhada com os times do projeto, com outros projetos ou com a empresa toda (inner source), e um projeto pode ficar isolado. Cada uma dessas combinações viraria mais um `if` nos handlers, e as listagens ("o que eu posso ver") teriam que percorrer o grafo inteiro em Python.

O Keycloak (ADR 0021) tem Authorization Services (UMA, políticas por role, grupo, tempo e JavaScript), que avaliam uma política por recurso. Eles não modelam relações entre objetos ("o projeto B consome este componente do projeto A") e não respondem `ListObjects`. O Keycloak não tem integração nativa com OpenFGA. Existem extensões da comunidade que copiam grupos e roles para o OpenFGA por event listener.

O ADR 0034 §3 decidiu tirar a autorização de `environments.py` para identity, o que ainda não foi feito.

## Decisão

**O OpenFGA é o ponto de decisão de autorização da Platform API. O Keycloak continua com a autenticação e os times. O projeto passa a ser a unidade onde ambientes e entidades de catálogo vivem, e o compartilhamento entre projetos é uma relação do modelo.**

### Papéis do Keycloak e do OpenFGA

- **O Keycloak autentica e mantém os times** (`/teams/<nome>`, ADR 0026). Nenhuma extensão do Keycloak é instalada.
- **A membership vai em cada pergunta como contextual tuples.** A API converte o `group_paths` do token em `user:<sub> member team:<t>` (só `/teams/*`) e `user:<sub> admin platform:wasp` (só `/platform-admins`), com a mesma regra de `groups_and_teams`: um grupo homônimo em outro path não concede nada. Os membros nunca são copiados para o OpenFGA, e a revogação demora no máximo o tempo de vida do token, como o ADR 0026 já aceitou.
- **O OpenFGA é uma projeção dos CRs.** O ADR 0022 continua valendo: os campos dos CRs (`spec.project`, anotação `owner`, `sharedWith`, `consumers`, `ownerTeam`) são a fonte da verdade. Um controller `authz` grava e apaga tuplas a partir deles. Uma store perdida é reconstruída a partir do cluster. No create, a API grava a tupla do dono de forma síncrona para que o criador enxergue o objeto na hora, e o controller converge depois, sem efeito duplicado.
- **Um ponto de entrada:** `authorize(principal, relation, object)` no módulo de identity. Cada subsistema escolhe a relação que cada rota exige. As listagens usam `ListObjects`.

### Projetos

- **CRD `Project`.** Quem cria é `owner`. Os times continuam globais, e o projeto vincula cada time com um papel fixo: `owner`, `admin`, `developer` ou `viewer`. Uma pessoa fora de time também pode ser vinculada.
- **`platform-admins` são `admin` de todo projeto**, por `admin from platform`.
- **Migração:** o `platform init` cria o projeto `default` e move para ele todos os objetos existentes.

### Compartilhamento

Uma relação, `consumer`, com três alcances:

- **No projeto:** implícito, por `viewer from project`.
- **Com outro projeto ou time:** `consumer: project:<p>#developer` ou `team:<t>#member`.
- **Com a empresa:** `consumer: platform:wasp#user`.

O consumidor vê e usa (depende da entidade, renderiza o template), mas não edita nem recompartilha. Editar e compartilhar ficam com os maintainers: membros do `ownerTeam` e admins do projeto.

Um ambiente continua privado dentro do projeto por padrão: os viewers do projeto o veem na listagem, mas o kubeconfig (ADR 0028) só vai para o dono, os times de `sharedWith` e os admins do projeto.

**Isolamento:** um projeto com `isolation: strict` não recebe nem concede grants que cruzem a fronteira do projeto. Quem aplica essa regra é a API, ao gravar o grant (409 com mensagem explícita), e não o modelo. Assim o modelo fica sem `but not` e a recusa é explicável.

### Modelo (rascunho)

```
model
  schema 1.1

type user

type team
  relations
    define member: [user]

type platform
  relations
    define admin: [user]
    define user: [user]

type project
  relations
    define platform: [platform]
    define owner: [user]
    define admin: [user, team#member] or owner or admin from platform
    define developer: [user, team#member] or admin
    define viewer: [user, team#member] or developer
    define can_create: developer
    define can_manage_members: admin

type environment
  relations
    define project: [project]
    define owner: [user]
    define shared_with: [team#member]
    define can_view: viewer from project
    define can_use: owner or shared_with or admin from project
    define can_delete: owner or admin from project
    define can_share: owner or admin from project

type component
  relations
    define project: [project]
    define owner_team: [team]
    define maintainer: member from owner_team or admin from project
    define consumer: [project#developer, team#member, platform#user]
    define can_view: viewer from project or consumer
    define can_use: developer from project or consumer
    define can_edit: maintainer
    define can_share: maintainer

type cloud_account
  relations
    define project: [project]
    define shared_with: [team#member, project#developer]
    define can_provision: admin from project or shared_with
```

`api`, `resource`, `template`, `system` e `domain` seguem o tipo `component`. `scm_connection` pertence ao projeto e exige `can_use` para criar um component.

### Cenários

Os cenários viram testes `.fga.yaml` (`fga model test`) no CI, junto do modelo em `platform/authz/`.

| # | Cenário | Esperado |
|---|---|---|
| 1 | Ana cria o projeto `checkout` | Ana é `owner`, e com isso `admin`, `developer` e `viewer` |
| 2 | `team-alpha` vinculado como `developer` em `checkout` | Um membro do alpha cria ambiente, mas não gerencia membros |
| 3 | Bob (alpha) cria `env-bob` em `checkout` | Carla (alpha) tem `can_view`, mas não `can_use` |
| 4 | Bob compartilha `env-bob` com `team-alpha` | Carla tem `can_use`. Ao sair do time, perde o acesso no próximo token |
| 5 | Componente `cart-api` (`ownerTeam` `team-alpha`) em `checkout` | `team-beta`, sem vínculo com o projeto, não vê o componente |
| 6 | `cart-api` com `consumer: project:payments#developer` | Os devs de `payments` veem e usam, mas não editam nem recompartilham |
| 7 | `cart-api` com `consumer: platform:wasp#user` | Qualquer usuário vê. `can_edit` continua só com os maintainers |
| 8 | `payments` é `strict` e alguém concede `consumer` a ele | A API recusa com 409 |
| 9 | Ambiente de `checkout` usa uma cloud account do projeto `infra` | Exige `can_provision`, via `shared_with: project:checkout#developer` |
| 10 | Membro de `platform-admins` | É `admin` de todo projeto |
| 11 | Grupo homônimo `/x/platform-admins` | Não concede nada |
| 12 | Apagar um time ainda vinculado | `users_of` responde por consulta reversa no OpenFGA |
| 13 | `platform environment list` | `ListObjects(can_view)`, sem kubeconfig na lista |

### Fatias

Issue pai #508. Ordem: #510 (predicados para identity, ADR 0034 §3), #511 (OpenFGA no `platform-local`, modelo e testes), #512 (autorização de ambientes pelo OpenFGA, com paridade e projeto `default` implícito), #513 (controller `authz`), #514 (CRD `Project` e `platform project`), #515 (ambientes no projeto), #516 (catálogo no projeto, com `consumers`), #517 (cloud accounts, SCM connections e `isolation: strict`) e #518 (`platform auth check|explain` e MCP).

## Decisões em aberto

Elas se fecham antes do status `Aceito`:

- **Projeto como namespace kube (`project-<nome>`) ou como label.** A recomendação é namespace: os controllers ganham isolamento natural, e o RBAC kube acompanha o projeto.
- **Papéis fixos ou customizáveis.** A recomendação é papéis fixos até aparecer um caso real.
- **Nome de ambiente por projeto ou global.** Um nome por projeto muda `vcluster.env-{name}` em `credentials.py` e no provider `workload`, e a faixa de portas `7100`–`7119` continua global.
- **O `can_use` de um consumidor inclui renderizar o template em outro projeto.** No rascunho, sim.

## Alternativas consideradas

- **Continuar com predicados em Python.** Funciona para dono e `sharedWith`, mas projetos, papéis herdados e compartilhamento entre projetos multiplicam os casos, e as listagens precisariam percorrer o grafo na API. Rejeitada.
- **Keycloak Authorization Services.** Não tem relação entre objetos nem `ListObjects`, e as políticas ficariam no realm, fora do repo e dos testes. Rejeitada.
- **Copiar a membership do Keycloak para o OpenFGA** (extensão de event listener). É mais um componente no Keycloak e uma segunda cópia dos membros para manter em sincronia, quando o token já os traz. Rejeitada enquanto a revogação no fim do token for aceitável.
- **OPA/Cedar (política por atributo).** Avaliam bem uma requisição isolada, mas não respondem "o que esta pessoa pode ver" sem carregar todos os objetos. Rejeitada para este modelo, que é de relações.

## Consequências

- A plataforma ganha um componente com estado (OpenFGA + Postgres) no caminho de toda rota `/v1/*`. Se ele cair, a API recusa (falha fechada), e `platform status` mostra a capability.
- As tuplas são consistentes só no fim: um compartilhamento feito por outro caminho aparece quando o controller converge. A API grava as tuplas das suas próprias escritas na hora.
- A regra de quem pode o quê sai dos handlers e fica num arquivo testável, `platform/authz/model.fga`, com os cenários acima como testes.
- `users_of` e as listagens deixam de percorrer os CRs.
- Os comandos passam a ter `--project` (com padrão na config da CLI). As páginas do walkthrough e da referência mudam a cada fatia.
