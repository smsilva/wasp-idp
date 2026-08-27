# aws_ec2_client_vpn_authorization_rule

|  |  |
|---|---|
| **Description** | One rule per authorized group and destination CIDR — this is where per-client isolation is actually enforced, not in routing. `target_network_cidr` is the whole supernet; the group id (`access_group_id`) is what narrows who reaches it. |
| **Provider** | `terraform · aws` (account `network`) |
| **Type** | `Client VPN authorization rule` |
| **Layer** | `04 · connectivity` |
| **State** | `connectivity` |
| **Dependencies** | `aws_ec2_client_vpn_endpoint.hub`; `for_each` over `var.operator_group_ids`, gated by `var.manage_authorization` |
| **Produces** | Nothing consumed further downstream — terminal in the graph |
| **Teardown** | No particular ordering constraint beyond preceding the endpoint |

## Examples

- `authorize_all_groups` is never used: setting it would let anyone who authenticates reach the target CIDR regardless of group membership, silently erasing "person A only reaches spoke A" with no error and no warning.
- Group ids come from Identity Center's `${user:groups}` SAML attribute, which returns UUIDs, not names — the group name is translated to a UUID by `generate-tfvars` before it ever reaches this variable, and the variable itself rejects anything that is not a UUID.
- A future per-client isolation proof (layer `08`) adds one rule per client group against its own spoke CIDR — the mechanism already exists here, only the CIDR narrows from "whole supernet" to "one spoke" as more rules are added.
