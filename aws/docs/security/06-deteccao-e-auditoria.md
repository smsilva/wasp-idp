# 06 — Detecção e Auditoria

**Pilar WAF principal:** Security (SEC04 — detecção).

## Prevenção falha em silêncio sem detecção

SCP, boundary e menor privilégio (tópicos 1–3) **previnem**. Mas nenhum controle é perfeito, e
uma policy permissiva demais, uma role órfã ou um acesso público acidental só viram problema
quando alguém percebe. Detecção é a camada que transforma "algo passou que não devia" em
**sinal auditável** — antes de virar incidente. É também como se **descobre** o menor
privilégio real (o inventário de ações de fato usadas), fechando o ciclo do tópico 1.

## As quatro fontes de sinal

| Fonte | Responde | Sempre ligada? |
|---|---|---|
| **CloudTrail** | "o que foi chamado, por quem, quando" — trilha de toda API call | **sim** (protegido por SCP — `../accounts/02`) |
| **IAM Access Analyzer** | "que recurso é acessível de fora da minha zona de confiança" | sim, por conta/Organization |
| **GuardDuty** | "há comportamento anômalo/malicioso" (threat intel, ML) | sim, recomendado |
| **Credential/Access reports** | "que credenciais existem, quais nunca foram usadas" | sob demanda |

## CloudTrail — a trilha de tudo

- Registra **cada** chamada de API (quem, qual ação, qual recurso, de qual IP, com sucesso ou
  `AccessDenied`). É a base forense e a resposta a "quem fez X?".
- Protegido por SCP na Root (`ProtectCloudTrail` — `../accounts/02`): nem um admin de
  conta-membro desabilita a trilha. Prevenção protegendo a detecção.
- **Uso para menor privilégio:** filtrar os eventos de uma identidade por um período mostra as
  ações que ela **de fato** usou → é o inventário para enxugar `PowerUserAccess` numa
  customer-managed policy escopada (o gancho deixado no tópico 1).

## IAM Access Analyzer — o alerta de perímetro

- **Findings de acesso externo:** varre resource policies (bucket, role, KMS, RAM) e sinaliza
  qualquer recurso acessível **fora** da zona de confiança (a conta ou a Organization). Um
  `Principal: "*"` sem `aws:PrincipalOrgID` (tópico 3) aparece aqui.
- **Policy validation:** valida a sintaxe/semântica de uma policy antes de aplicar (avisa de
  `Resource: "*"` largo, ações inexistentes, `Sid` duplicado).
- **Unused access:** aponta roles/permissões não usadas há N dias → candidatos a remover
  (SEC03-BP04, reduzir permissões continuamente).

## GuardDuty — anomalia e ameaça

Detecção contínua baseada em CloudTrail, VPC Flow Logs (`../network/06`) e DNS logs, com threat
intel e ML: uso de credencial de uma região/IP incomum, exfiltração, reconhecimento. Não
substitui os anteriores — é a camada de **comportamento** sobre a de **configuração**.

## Como isso fecha o ciclo do perímetro

```text
Tópicos 1-5  PREVINEM   (SCP, boundary, menor privilégio, roles escopadas, auth de VPN)
Tópico 6     DETECTA    (CloudTrail: o que passou; Access Analyzer: o que está exposto;
                         GuardDuty: o que é anômalo)
   └─► achado alimenta de volta a prevenção:
       - acesso externo inesperado  → apertar resource policy (tópico 3)
       - permissão nunca usada       → remover da identity policy (tópico 1)
       - ação negada recorrente      → a policy está errada OU há tentativa indevida
```

Detecção sem realimentar a prevenção é só ruído — cada finding deve virar um ajuste de policy
ou uma decisão consciente de aceitar o risco.

## Estado nesta PoC

- **CloudTrail:** protegido por SCP na conta de validação (`ProtectCloudTrail`, `<scp-id>`);
  trilha da conta ainda não auditada nesta doc.
- **Access Analyzer / GuardDuty:** ainda não habilitados no escopo do PoC — itens do alvo, não
  do estado atual. Habilitar é passo de conta/Organization (barato; sem provisionamento de
  workload).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **SEC04-BP01** capturar logs/eventos | CloudTrail + VPC Flow Logs (`../network/06`) sempre ligados |
| **SEC04-BP02** analisar centralmente | Access Analyzer por Organization; GuardDuty agregado |
| **SEC04-BP03** automatizar resposta a achados | finding → ajuste de policy (ciclo prevenção↔detecção) |
| **SEC03-BP04** reduzir permissões | Access Analyzer unused access + CloudTrail para inventário real |

## Próximo

→ [`07-mapa-crossplane.md`](07-mapa-crossplane.md): o que deste domínio vira XRD/Composition e
o que fica manual (o bootstrap de IAM).
