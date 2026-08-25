# 07 — CloudTrail organizacional e conta Log Archive

**Pilar WAF principal:** Security ([SEC04](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/detection.html) — detecção). Também Operational Excellence
(rastro de auditoria do próprio bootstrap).

> **Ordem de execução ≠ ordem de leitura.** Este é o último arquivo do domínio, mas na
> [sequência de construção](CLAUDE.md) ele vem **antes** de criar OUs e contas de projeto:
> sem trilha desde o início, não existe rastro de quem fez o quê durante o bootstrap — e
> é justamente aí que se toca em tudo com privilégio máximo.

## Por que a trilha mora em outra conta

Um log de auditoria só vale se quem é auditado não puder apagá-lo. Se o bucket do
CloudTrail vive na management account ou na conta de rede, qualquer admin daquela conta
apaga o rastro do que fez. Por isso o whitepaper *Organizing Your AWS Environment Using
Multiple Accounts* separa:

| OU | Conta | Papel |
|---|---|---|
| `Security` | `log-archive` | **Só recebe** logs. Ninguém opera workload aqui; idealmente acesso só de leitura, exceto break-glass. |
| `Security` | `security-tooling` | Delegated admin de GuardDuty/Security Hub/Config — quem **lê** os logs e gera alerta. |
| `Infrastructure` | `network` | Hub de conectividade. Não guarda log de auditoria. |

A separação `log-archive` (armazena) × `security-tooling` (analisa) é o mesmo princípio
aplicado uma camada abaixo: quem investiga não precisa poder deletar o acervo.

## Trail organizacional em uma frase

Um trail criado na **management account** com `--is-organization-trail` captura os eventos
de **todas** as contas-membro, inclusive as criadas depois — a conta nova entra sozinha, sem
passo de onboarding. Escrever em um bucket de outra conta é o comportamento normal do
serviço; o que autoriza é a **bucket policy**, não uma role.

Também use `--is-multi-region-trail`: eventos de uma região que você não usa são exatamente
os que interessam num incidente.

## Pré-requisitos

```bash
scripts/enable-service-access --service cloudtrail.amazonaws.com
```

Sem esse trusted access, `create-trail --is-organization-trail` falha.

## Como o bucket é configurado

`scripts/create-log-archive-bucket` roda a partir da management account, assume
`OrganizationAccountAccessRole` na `log-archive` e aplica:

| Configuração | Porquê |
|---|---|
| Block Public Access (4 flags) | Um bucket de auditoria público é um incidente por si só |
| Versionamento | Sobrescrita não destrói a versão anterior |
| SSE-S3 + Bucket Key | Criptografia em repouso sem custo de KMS por objeto |
| `BucketOwnerEnforced` | Desliga ACLs — a policy é a única fonte de autorização |
| Bucket policy | `s3:GetBucketAcl` + `s3:PutObject` para `cloudtrail.amazonaws.com`, e `Deny` em tráfego não-TLS |

### O detalhe que mais quebra: os dois prefixos

A policy de escrita precisa de **dois** `Resource`, não um:

```text
arn:aws:s3:::<bucket>/AWSLogs/<management-account-id>/*
arn:aws:s3:::<bucket>/AWSLogs/<organization-id>/*
```

O trail organizacional grava os eventos das contas-membro sob o **id da Organization**
(`o-xxxxxxxxxx`), e os da própria management account sob o **id da conta**. Com só o
segundo prefixo, o trail sobe e parece saudável — mas nenhum evento de conta-membro é
gravado.

### `aws:SourceArn` amarra a policy ao trail

Ambas as statements condicionam a `aws:SourceArn` do trail. Isso impede o *confused
deputy*: outra conta não consegue apontar um trail dela para o seu bucket. O efeito
colateral é que **renomear o trail invalida a policy** — rodar o script de novo com o novo
`--trail`.

## Criando o trail

```bash
scripts/create-organization-trail
```

`create-trail` **não** começa a gravar sozinho — `start-logging` é um segundo passo, fácil
de esquecer, e um trail parado tem exatamente a mesma aparência de um trail saudável na
listagem (`describe-trails` não mostra estado; só `get-trail-status`). O script sempre
reafirma o `start-logging`.

Também liga `--enable-log-file-validation`: o CloudTrail passa a publicar arquivos digest
assinados, que provam depois que nenhum log foi alterado ou removido. Sem isso, um acervo
imutável por policy ainda não é um acervo **verificável**.

## Acesso à conta log-archive

Conta recém-criada não está no portal SSO. O gancho de bootstrap é a
`OrganizationAccountAccessRole` (`04-acesso-cross-account.md`); o passo definitivo é
atribuir um permission set:

```bash
scripts/assign-permission-set --account log-archive --user <username>
```

Para a `log-archive` especificamente, o permission set correto no dia a dia é
`ReadOnlyAccess`, não `AdministratorAccess` — o valor da conta vem de ninguém poder
apagar o que está lá.

## Custo

O que acabou de ser ligado é a configuração **grátis ou quase** — o que custa é o que se
adiciona depois.

| Item | Preço (us-east-1) | Nesta Organization |
|---|---|---|
| Management events, 1ª cópia por conta | **US$ 0** | O trail organizacional consome essa cota grátis em cada conta-membro |
| Management events, cópias adicionais | US$ 2,00 / 100k eventos | US$ 0 — só existe um trail |
| S3 Standard (armazenamento) | US$ 0,023 / GB-mês | Org pequena e pouco ativa gera na casa das dezenas de MB/mês → **centavos** |
| S3 PUT (entrega dos arquivos) | US$ 0,005 / 1k requests | Entrega a cada ~5 min **por conta e por região com atividade**; região ociosa quase não entrega |
| Digest de validação de integridade | incluso | — |

Ordem de grandeza para esta Organization hoje (4 contas, tráfego de bootstrap):
**menos de US$ 1/mês**, e o crescimento acompanha o número de contas ativas, não o tamanho
dos workloads.

### O que faz a conta explodir

| Recurso | Preço | Por que cuidar |
|---|---|---|
| **Data events** (S3 object-level, Lambda invoke, DynamoDB) | US$ 0,10 / 100k eventos | Um bucket movimentado gera milhões de eventos/dia. Habilitar **só** com seletor escopado a recursos específicos — nunca "todos os buckets" |
| **CloudTrail Insights** | US$ 0,35 / 100k write events analisados | Cobra sobre o volume analisado, não sobre as anomalias encontradas |
| **CloudTrail Lake** | US$ ~2,50 / GB ingerido + retenção | Substitui a análise ad-hoc por SQL, mas é outra ordem de grandeza |
| **Segundo trail** | US$ 2,00 / 100k eventos | Duplicar o trail para outro destino deixa de ser grátis |

Regra prática: **management events em todas as contas, sempre; data events só onde houver
uma pergunta específica a responder.**

### Retenção

O custo de S3 é o único que cresce sozinho, indefinidamente. Uma lifecycle rule
(Standard → Glacier Instant/Flexible após 90–180 dias, expiração após N anos) resolve, mas
a janela de retenção é decisão de compliance, ainda **não tomada** nesta referência — por
isso o bucket nasce sem lifecycle.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC04-BP01](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_detect_investigate_events_app_service_logging.html)** configurar log de serviço | Trail organizacional multi-region, todas as contas, incluindo as futuras |
| **[SEC04-BP02](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_detect_investigate_events_logs.html)** log centralizado e imutável | Bucket em conta separada, versionado, sem acesso de escrita para quem é auditado |
| **[SEC01-BP01](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_multi_accounts.html)** separação por conta | `log-archive` isolada em OU `Security`, fora de `Infrastructure` e `Workloads` |

## Próximo

→ Retomar a [sequência de construção](CLAUDE.md) no passo de SCPs
([`02-guardrails-scp.md`](02-guardrails-scp.md)) — com o rastro já ligado.
