# Teams

Um time é um grupo do Keycloak que a Platform API mantém (ADR 0026). É ele que compartilha ambientes e é dono de entidades do catálogo. Qualquer usuário lista e vê os times; criar, apagar e mudar membros é só para `platform-admins`.

```bash
platform team create team-alpha

platform team member add team-alpha voce@example.com

platform team get team-alpha
```

```
✓ team team-alpha created
✓ voce@example.com added to team-alpha
team-alpha: 1 member(s)
EMAIL             USERNAME
voce@example.com  voce@example.com
```

Um time em uso, dono de entidades do catálogo ou com ambientes compartilhados, não é apagado (`409`). O membro precisa ter entrado na plataforma uma vez, com o e-mail verificado: antes disso, o Keycloak não o conhece e a API responde `404`. O time chega ao token no próximo `platform login`, e o `platform whoami` passa a mostrá-lo junto dos grupos.

## Compartilhar um ambiente

Um ambiente nasce privado. Quem o criou pode compartilhá-lo com os times de que faz parte; com outros times, só `platform-admins`.

```bash
platform environment create review \
  --profile ephemeral \
  --share-with team-alpha \
  --wait

platform environment share greetings-test --team team-alpha

platform environment unshare greetings-test --team team-alpha
```

```
✓ review ready
✓ greetings-test shared with team-alpha
✓ greetings-test no longer shared with team-alpha
```

Os membros do time veem o ambiente no `environment list` e recebem o kubeconfig no `environment get`. Apagar, compartilhar e descompartilhar continuam com o dono e os admins.

Cada pessoa usa a própria identidade no vcluster ([usar o ambiente](06-use-environment.md)). Descompartilhar apaga as identidades de quem não é o dono, e tirar alguém do time apaga a dessa pessoa nos ambientes compartilhados com ele. Em segundos, o kubectl dessas pessoas passa a receber `environment 'greetings-test' is not yours nor shared with your teams`. Quem continua com acesso por outro time ganha um token novo no comando seguinte, sem perceber.
