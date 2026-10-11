# Environment personal credentials: short-lived tokens issued by the Platform API

**Status:** Aceito (2026-10-11). Substitui a fatia 2 ("Kubeconfig") do ADR 0026.

## Contexto

O ADR 0026 entregou o compartilhamento de ambientes com times em duas fatias. Na fatia 1 (#232), o dono e os membros dos times de `spec.sharedWith` recebem o mesmo kubeconfig de administrador do vcluster, com certificado de cliente. Quem sai do time perde o acesso pela API, mas continua com a credencial que já baixou, até o ambiente ser recriado.

A fatia 2 (#233) previa OIDC no API server do vcluster: aceitar o token do Keycloak, com RBAC por grupo e o plugin `kubectl oidc-login`. O Kubernetes exige um issuer HTTPS, igual ao `iss` do token, e acessível de dentro do vcluster. Hoje o issuer é `http://localhost:8180/realms/platform`. Para chegar lá, seria preciso:

- servir o Keycloak em HTTPS com uma CA local;
- trocar o `iss` na CLI, na Platform API e no smoke;
- instalar a CA no navegador, ou aceitar o aviso de certificado em todo login;
- trocar o redirect URI do Google OAuth no console do GCP;
- exigir um plugin externo do kubectl.

Tudo isso só para o perfil local.

Dois fatos testados no vcluster 0.37 (Kubernetes 1.36) abrem outro caminho:

- A Platform API alcança o API server de cada vcluster por dentro do cluster, em `https://vcluster.env-<nome>:<porta>`, e o certificado servido já inclui esse nome.
- Um token de ServiceAccount emitido por TokenRequest deixa de valer cerca de 10 s depois que a ServiceAccount é apagada. O token fica preso ao UID da ServiceAccount.

## Decisão

**A Platform API emite para cada pessoa uma credencial curta do vcluster, sob demanda, depois de conferir `can_use`. O kubeconfig entregue não traz credencial estática: ele chama `platform environment credential <nome>` como plugin `exec` do kubectl.**

- **Identidade:** cada pessoa é uma ServiceAccount no namespace `platform-identities` do vcluster. O nome dela é o `sub` do token, o mesmo valor que a anotação `owner` usa, e o e-mail fica numa anotação, só para exibição. No vcluster, a pessoa aparece como `system:serviceaccount:platform-identities:<sub>`.
- **Emissão:** `POST /v1/environments/{nome}/credentials` confere `can_use` com o token do Keycloak atual. Em seguida, cria a ServiceAccount e o `ClusterRoleBinding` dela, se ainda não existem, e devolve um TokenRequest de 10 minutos, o mínimo que o Kubernetes aceita. A API fala com o vcluster usando o kubeconfig de administrador que o provider já publica em `status.kubeconfigData`. O provider não muda.
- **Permissão no vcluster:** `cluster-admin`, o mesmo poder da fatia 1. A API é a porta de entrada: quem passa por `can_use` usa o ambiente inteiro. Não há RBAC por time dentro do vcluster.
- **Revogação:** em cada emissão, a API confere o token do Keycloak do momento. Ao tirar um time de `sharedWith`, a API apaga as ServiceAccounts de todos que não são o dono, e quem ainda tem acesso por outro time recebe um token novo na próxima chamada do kubectl. Ao tirar alguém de um time, a API apaga a ServiceAccount dessa pessoa nos ambientes compartilhados com o time, salvo os ambientes de que ela é dona. No pior caso, o acesso dura até a validade do access token do Keycloak, alguns minutos.
- **Kubeconfig:** `kubeconfigData` passa a ser o kubeconfig pessoal, montado pela API com o endereço e a CA do vcluster e um usuário `exec` (`client.authentication.k8s.io/v1`, `interactiveMode: Never`). Ao gravar o arquivo, a CLI troca o comando `platform` pelo caminho do executável que está rodando, para que o kubectl ache a mesma instalação. O kubeconfig de administrador sai só por `GET /v1/environments/{nome}/admin-kubeconfig`, restrito a `platform-admins`.
- **CLI:** `platform environment credential <nome>` imprime um `ExecCredential` e não guarda o token em disco. Cada processo do kubectl o chama uma vez. Se o token for revogado, o kubectl recebe 401, chama o plugin de novo e passa por uma nova checagem. `platform environment get <nome> --admin` grava o kubeconfig de administrador.

## Consequências

- Não há HTTPS, CA local, plugin externo ou mudança no login. Para o kubectl, basta ter a CLI `platform` instalada e logada.
- A Platform API passa a falar com o API server de cada vcluster. Se o vcluster não responde, a emissão falha com 503, mas o ambiente continua listado.
- Cada processo do kubectl gasta uma chamada à API e um TokenRequest. Ferramentas de longa duração (k9s, IDEs) renovam o token pelo próprio `expirationTimestamp`.
- A identidade no vcluster é uma ServiceAccount, não um `User`. Os audit logs registram `system:serviceaccount:platform-identities:<sub>`, e o e-mail fica na anotação da ServiceAccount.
- RBAC fino dentro do ambiente, como leitura para um time e escrita para outro, fica fora desta decisão. Se for preciso, o caminho é ligar os bindings ao time pelo qual a pessoa passou em `can_use`.
- Num alvo com HTTPS de verdade (AWS), OIDC no API server continua possível. Esta decisão vale para o perfil local e não impede essa troca.
