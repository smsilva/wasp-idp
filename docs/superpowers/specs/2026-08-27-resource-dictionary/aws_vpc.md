# aws_vpc

|  |  |
|---|---|
| **Description** | A `/16` carved out of the `10.0.0.0/12` supernet — the root of the network layer and the single irreversible decision in the provisioning chain. In `network-foundation` this is the hub VPC (`10.1.0.0/16` in `us-east-1`, `10.3.0.0/16` in `us-west-2`); the same module instantiates it again in `control-plane` as the first spoke (`10.2.0.0/16`). |
| **Provider** | `terraform · aws` |
| **Type** | `VPC` |
| **Layer** | `02 · network-foundation` |
| **State** | `network-foundation` (one root per region) / reused verbatim by `control-plane` |
| **Dependencies** | `None` (network root) |
| **Produces** | `vpc_id`, `vpc_cidr` — consumed by every subnet, gateway, route table, and later by layer 04's TGW attachment and data-source reads |
| **Teardown** | Must be empty of all dependents (subnets, gateways, attachments) first; the hub instance is otherwise `Permanent` in practice — kept up at zero cost |

## Examples

- The hub VPC is deliberately zero-cost and permanent: `enable_nat_gateway = false`, so nothing bills until a TGW exists to route through it.
- Cross-layer reads of this VPC (layers 04/05) go through `data "aws_vpc"` filtered by tag/name, never `terraform_remote_state` — the reading side survives a backend or key change on the writing side.
- The same `src/network` module is reused verbatim by `control-plane`, but with `enable_nat_gateway = true` there, since the spoke does need real egress.
