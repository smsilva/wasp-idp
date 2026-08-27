# aws_route53_record

|  |  |
|---|---|
| **Description** | The DNS validation record ACM asks for, written into the nonprod subzone. In layer 04 it proves ownership of the VPN certificate's domain; the same resource type recurs in layer 07 for the cluster wildcard's validation. |
| **Provider** | `terraform · aws` |
| **Type** | `Route 53 Record` |
| **Layer** | `04 · connectivity` |
| **State** | `connectivity` (VPN validation record) / `control-plane` (cluster wildcard validation, layer 07) |
| **Dependencies** | `aws_acm_certificate.vpn` (its `domain_validation_options`), `data.aws_route53_zone.subzone` (layer 03) |
| **Produces** | `fqdn` — consumed by `aws_acm_certificate_validation.vpn.validation_record_fqdns` |
| **Teardown** | Torn down with this root every night; `allow_overwrite = true` because the record is ephemeral by nature — recreating the certificate each time is expected, not an incident |

## Examples

- Short TTL (60s), same reasoning as the parent-zone NS delegation: the subzone-backed certificate is recreated with this layer every night, and a stale cached validation record would waste the first minutes of every morning's apply.
- Indexed as `tolist(...)[0]` rather than `for_each` over `domain_validation_options` — safe only because there is exactly one domain on the certificate; the official provider example's `for_each` pattern needs map keys known at plan time, which a computed attribute cannot give with a single indexed access.
- `allow_overwrite = true` is deliberate: this record's only job is to exist long enough for ACM to see it, and overwriting on every recreate is the correct behavior, not a drift smell.
