# Internal Products (IP)

Objetivo da plataforma além do MVP 1, na visão do usuário (2026-10-08): **estimular a criatividade e facilitar a criação de produtos novos dentro da organização**, como acontece com produtos que nascem como ideias. **IP = Internal Product**: aplicação ou solução criada internamente.

## A jornada de uma ideia

Qualquer pessoa da empresa tem uma ideia e:

1. **Registra** na plataforma (vira entidade do catálogo, com dono).
2. **Provisiona** recursos e faz **deploy**.
3. **Testa** e **monitora**.
4. **Refina**.
5. **Compartilha** com o restante da organização.

## Compartilhar = mudar de lifecycle

O Backstage já tem o campo `spec.lifecycle` em Component, API, Resource e System, com três valores bem conhecidos: `experimental`, `production` e `deprecated` ([doc](https://backstage.io/docs/features/software-catalog/descriptor-format)). Hoje todo o catálogo do repo está em `experimental`.

Proposta (ideia do usuário, não decidida):

| Lifecycle | Significado para um IP |
|---|---|
| `experimental` | Ideia em construção: o dono provisiona, testa e refina |
| `production` | **Validado e compartilhado** com a organização: outros times podem depender dele |
| `deprecated` | Em descontinuação: quem depende recebe aviso e prazo |

A mudança de lifecycle pode virar **gate da plataforma**: subir para `production` exige o que a organização pede de um produto compartilhado (dono, observabilidade, custo atribuído, segurança).

## Relação com o shaping `idp-cloud`

O segmento do shaping são squads que constroem IPs ou querem iniciar POC/MVP, times de 3–4 pessoas sem operação dedicada; a North Star é o tempo do pedido ao primeiro deploy funcional.

## Uso na apresentação

- **Ato `problem`:** o objetivo não é só provisionar ambiente mais rápido; é **levar uma ideia a produto**.
- **Developer Control (`declare-identity`):** o `lifecycle: experimental` do arquivo vira o gancho para o ciclo de vida do IP.
