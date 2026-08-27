# ou-structure

|  |  |
|---|---|
| **Description** | The five Organizational Units this reference groups accounts under: `Security`, `Infrastructure`, `Deployments`, `Workloads/NonProd`, `Workloads/Production`. OUs are the attachment point for Service Control Policies — an SCP cannot target a single account's "role" directly, only the OU it lives in. |
| **Provider** | `aws-cli (scripts/create-organizational-unit-structure)` |
| **Type** | `Organizational Unit ×5` |
| **Layer** | `00 · accounts` |
| **Dependencies** | `organization` |
| **State** | `—` |
| **Produces** | One OU id per OU — the `--target-id` for `baseline-scps`, and the `--destination-parent-id` for every `move-account` in the account-creation sequence behind `organization-account-access-role` |
| **Teardown** | Every account must be moved out (or removed) before an OU can be deleted; `Workloads` and its two sub-OUs nest, so the sub-OUs go first |

## Examples

- Naming follows the whitepaper *Organizing Your AWS Environment Using Multiple Accounts*, not the Well-Architected Framework — the WAF never names an OU or account, it only justifies isolating by account.
- Renaming an OU (`update-organizational-unit`) preserves its Id, so SCP attachments and member accounts stay valid — safe to do after the fact, unlike renaming an account's root e-mail.
- `Workloads/NonProd` and `Workloads/Production` inherit the SCPs attached to `Workloads` without their own attachment.
