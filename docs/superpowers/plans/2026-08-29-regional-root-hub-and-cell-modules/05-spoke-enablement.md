# Fase 5 — fechar o degrau entre "control plane de pé" e "spoke provisionado"

As fases 1-4 entregam a região: hub, célula, EKS, e o Crossplane instalado com Pod Identity. O que
elas **não** entregam é o outro lado do assume role — e sem ele o Crossplane sobe saudável e o
primeiro Composition morre com `AccessDenied`.

**Esta fase é independente das quatro anteriores** e pode ser executada em paralelo à 2 e à 3: ela
não toca em `regions/`, `src/hub` nem `src/cell`. O que ela consome das outras é **um nome** — o da
role de Pod Identity da célula, que a fase 3 regionaliza.

**Pré-requisito de leitura:** [`08-control-plane-identity.md`](../../../../aws/docs/security/08-control-plane-identity.md),
que já desenhou a trust policy correta (ExternalId + `aws:PrincipalArn`) e nunca virou código.

**Issues:** [#38](https://github.com/smsilva/wasp-idp/issues/38) (Task 1) e
[#39](https://github.com/smsilva/wasp-idp/issues/39) (Task 2). A #39 depende da #38 para ter o que
documentar.

---

## O que já sabemos, verificado no código

Registrado aqui para que nenhuma task comece por redescobrir:

| Fato | Onde |
|---|---|
| A Pod Identity da célula autoriza `sts:AssumeRole` + `sts:TagSession` em `arn:aws:iam::<alvo>:role/crossplane-*` | `control-plane/main.tf:461-477` |
| A lista de contas-alvo vem de `var.target_account_ids` e chega ao cluster pelo ConfigMap `platform-bootstrap`, chave `targetAccountIds` | `control-plane/main.tf:677-700` |
| O nome de role que o ProviderConfig espera na conta-alvo é `crossplane-<nome-do-spoke>` | `aws/eks/providers/provider-config-wasp-nonprod.yaml`, `assumeRoleChain[0].roleARN` |
| **Nada cria essa role.** O único artefato é `aws/eks/providers/spoke-trust-policy.json`, que **nenhum script aplica** — a única referência a ele no repo é um comentário | `grep -rn spoke-trust-policy aws/` devolve 1 hit, num comentário YAML |
| E ele está **obsoleto**, não só ausente: confia em `arn:aws:iam::<network>:user/crossplane-poc`, o IAM user da era k3d. A célula em EKS assume pela role de Pod Identity, que é outro principal | `aws/eks/providers/spoke-trust-policy.json` |
| Não há `ExternalId` nem condição `aws:PrincipalArn` na trust policy existente | idem |
| `aws/docs/bootstrap/` inteiro descreve o mundo k3d: criar o IAM user, anexar `PowerUserAccess`, gerar access key, gravar em `poc-idp/crossplane-poc-credentials` | `aws/docs/bootstrap/00-crossplane-iam-user.md`, `CLAUDE.md` |

**A consequência prática:** hoje o caminho `célula → conta-alvo` está quebrado dos dois lados. O lado
de origem foi consertado quando a célula migrou para EKS com Pod Identity; o lado de destino ficou
apontando para o principal antigo. Nenhum teste pega isso — só um Composition real.

---

## Onde o invariante da região morde aqui

A role de destino é **por conta-alvo, não por região**: `crossplane-wasp-nonprod` serve as células de
todas as regiões. Mas a trust policy dela lista os principais de origem, e **esses são por região**,
porque a fase 3 regionaliza o nome da célula:

```
arn:aws:iam::<cicd>:role/control-plane-us-east-1-crossplane
arn:aws:iam::<cicd>:role/control-plane-us-west-2-crossplane
```

Uma trust policy que liste só a `us-east-1` faz a segunda região falhar com `AccessDenied` no assume
— o modo de falha mais caro de diagnosticar da cadeia, porque tudo *parece* de pé. A trust policy tem
de aceitar **uma lista** de principais de origem, gerada a partir das regiões existentes, não um ARN
escrito à mão.

E a tentação errada, que a Task 1 tem de recusar explicitamente: `Principal: {"AWS": "arn:aws:iam::<cicd>:root"}`
resolve o problema de listar regiões — e autoriza **qualquer** principal da conta `cicd` a entrar na
conta-alvo. É a troca que `08-control-plane-identity.md` já rejeitou.

---

### Task 1: a role `crossplane-<alvo>` nas contas-alvo

**Files:**
- Create: `aws/terraform/targets/<...>` — raiz nova, ou um `src/crossplane-target` consumido por ela
- Delete: `aws/eks/providers/spoke-trust-policy.json` (obsoleto; o Terraform passa a ser a fonte)

**Interfaces:**
- Consumes: os ARNs das roles de Pod Identity das células (uma por região), e `target_account_ids` do
  `values.tfvars`.
- Produces: em cada conta-alvo, uma role `crossplane-<nome>` assumível **só** pelas células.

**Decisão em aberto, a resolver antes de escrever código:** esta é uma raiz própria (`targets/`) ou um
módulo dentro de `regions/<r>/`? Argumento para raiz própria: a role é por conta-alvo, não por
região; duas regiões criando a mesma role colidem. Argumento para dentro da região: um `apply` só.
**A raiz própria vence** — é a mesma lógica que mantém `dns/` fora da região, e é o que evita que
derrubar a `us-east-1` remova o acesso da `us-west-2`. Registrar a escolha em ADR se ela mudar.

- [ ] **Step 1: a trust policy, escopada nos três eixos**

```hcl
data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole", "sts:TagSession"]

    principals {
      type        = "AWS"
      identifiers = var.control_plane_role_arns   # uma por regiao, NUNCA <conta>:root
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.external_id]
    }
  }
}
```

Os três escopos, e por que nenhum é redundante:

| Escopo | Sem ele |
|---|---|
| `principals` com os ARNs das roles, não `:root` | qualquer principal da conta `cicd` alcança a conta-alvo |
| `sts:ExternalId` | confused deputy — ver [`02-cross-account-roles.md`](../../../../aws/docs/security/02-cross-account-roles.md) |
| lista de ARNs, não um só | a segunda região falha no assume, com tudo aparentando estar de pé |

`sts:TagSession` entra junto porque a policy de origem já o concede (`control-plane/main.tf:470`) —
uma permite tagear, a outra tem de aceitar; conceder de um lado só dá `AccessDenied` que não menciona
tags.

- [ ] **Step 2: teste de duas execuções sobre a lista de principais (invariante)**

O mesmo padrão das fases 1-3: um run com uma região na lista, outro com duas, asserindo que o
`aws_iam_role.this.assume_role_policy` contém os dois ARNs no segundo. Mutação obrigatória: fixar um
ARN literal e ver o segundo run falhar.

- [ ] **Step 3: a permission policy da role de destino**

`PowerUserAccess` é o que a era k3d usava, e é grosseiro de propósito enquanto for PoC — mas agora ele
vive numa conta que **não** é a `network`, o que muda o raciocínio. Decidir e escrever por quê: o
mínimo real são as actions das Compositions que existem (`aws/platform/charts/spoke`), e essa lista é
curta o bastante para ser explícita.

- [ ] **Step 4: apagar o artefato obsoleto e corrigir quem o cita**

```bash
cd /home/silvios/git/wasp-idp
git rm aws/eks/providers/spoke-trust-policy.json
grep -rn 'spoke-trust-policy\|crossplane-poc' aws/ --exclude-dir=logs --exclude-dir=archived
```

Cada hit sobrevivente é um leitor futuro sendo mandado criar uma access key que ninguém consome.

- [ ] **Step 5: aceite real — um Composition atravessa**

O único teste que vale: aplicar um Composition que crie um recurso barato na conta-alvo (um bucket
S3, uma subnet) e ver o objeto ficar `READY=True`. `AccessDenied` aqui aponta para trust policy;
`READY` com `SYNCED=False` aponta para permission policy.

---

### Task 2: `aws/docs/bootstrap/` reescrito para o mundo Pod Identity

**Files:**
- Rewrite: `aws/docs/bootstrap/00-crossplane-iam-user.md`, `aws/docs/bootstrap/CLAUDE.md`
- Modify: `aws/docs/security/08-control-plane-identity.md` — **não**, ver Step 3

**Interfaces:**
- Consumes: a role da Task 1.
- Produces: um domínio de docs que descreve o que existe.

- [ ] **Step 1: o que ficou falso**

O domínio inteiro descreve o "galinha-e-ovo" da era k3d — a automação não pode se auto-conceder IAM,
então um humano cria o IAM user `crossplane-poc` com access key. **O EKS resolveu esse galinha-e-ovo:**
Pod Identity dá identidade sem credencial de longa duração, e a role é criada pelo mesmo Terraform que
cria o cluster. O passo manual que sobra é outro e é menor.

| Hoje diz | Verdade depois da fase 4 |
|---|---|
| criar IAM user `crossplane-poc` | não existe; a identidade é a role de Pod Identity da célula |
| anexar `PowerUserAccess` + inline policy | a policy é `control-plane/main.tf:461-477`, versionada |
| gerar access key e gravar em `poc-idp/crossplane-poc-credentials` | não há access key |
| "o único passo imperativo e não-automatizável desta arquitetura" | o único passo manual restante é o app SAML no Identity Center, que é outro domínio |

- [ ] **Step 2: o que o domínio passa a ser**

Duas opções, e a escolha é de quem executa: **apagar** `aws/docs/bootstrap/` e mover o que sobra para
`aws/docs/accounts/` (a fundação) e `aws/docs/security/` (a identidade); ou **reescrevê-lo** como o
bootstrap que de fato existe — a role da Task 1 na conta-alvo.

Recomendação: **reescrever**, mantendo o nome. Continua havendo um bootstrap manual e ele continua
sendo circular — alguém com `AdministratorAccess` na conta-alvo precisa criar a primeira role, porque
o Crossplane não pode se conceder o acesso que o autoriza. Só que o artefato mudou de "IAM user com
access key" para "role com trust policy", e agora é Terraform.

- [ ] **Step 3: o ADR e os docs de segurança não se editam retroativamente**

`08-control-plane-identity.md` não é ADR e pode ser corrigido — mas o trecho "a aposentadoria do IAM
user está bloqueada pela migração do control plane para EKS" virou **história**, não limitação. Marcar
como resolvido com data, em vez de apagar: o argumento previu corretamente o desbloqueio, e apagá-lo
esconde que a previsão se confirmou.

O que **não** se edita: `docs/adr/`. Se a decisão sobre `PowerUserAccess` na conta-alvo divergir do
que algum ADR aceito diz, é ADR novo.

---

### Task 3: a pergunta que fica em aberto, escrita antes de ser esquecida

**Files:**
- Modify: `aws/docs/open-questions.md`

- [ ] **Step 1: quem aceita o attachment do TGW do spoke criado por Crossplane?**

Hoje, na célula, o attachment cross-account tem os dois lados no mesmo `terraform apply`:
`aws_ec2_transit_gateway_vpc_attachment` na conta da célula e
`aws_ec2_transit_gateway_vpc_attachment_accepter` na conta `network`, com provider aliasado
(`control-plane/main.tf:108` e `:141`).

Quando o Crossplane criar a VPC de um spoke de workload, o lado de aceite fica sem dono. As saídas
possíveis, nenhuma escolhida:

1. O Crossplane assume uma role **também na conta `network`** — mas `target_account_ids` hoje não
   contempla esse caso, e dar ao control plane um pé na conta de rede é exatamente o que a separação
   de contas existe para evitar.
2. Auto-accept no TGW, escopado por RAM share — a `aws_ram_resource_association` já existe; falta
   avaliar se `auto_accept_shared_attachments` pode ser ligado sem virar "qualquer conta do share
   anexa o que quiser".
3. Um controlador na conta `network` que aceita attachments marcados com uma tag conhecida — mais
   peça móvel, mas é o único que mantém a decisão do lado de quem é dono da malha.

Escrever as três em `open-questions.md` com este contexto. **Não decidir aqui:** a decisão depende de
como o spoke de workload vai ser modelado, que é outra frente.

---

## Aceite da fase 5

- [ ] Um Composition aplicado no control plane cria um recurso real numa conta-alvo e fica
      `READY=True` — o aceite que nenhum teste offline substitui.
- [ ] A trust policy da role de destino não contém `:root` e exige `ExternalId`.
- [ ] **(invariante)** A trust policy lista os principais de **todas** as regiões com célula, e o
      teste de duas execuções prova que a lista vem por referência.
- [ ] `grep -rn 'crossplane-poc' aws/ --exclude-dir=logs --exclude-dir=archived` não devolve nada
      fora de docs históricas.
- [ ] `aws/docs/bootstrap/` descreve o bootstrap que existe, e `08-control-plane-identity.md` marca
      como resolvido — com data — o bloqueio que a migração para EKS levantou.
- [ ] As três saídas para o aceite do attachment do spoke estão em `open-questions.md`, com o
      contexto que hoje só existe nesta conversa.
