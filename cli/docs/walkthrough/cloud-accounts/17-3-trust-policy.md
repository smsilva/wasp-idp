# Apply the trust policy

Until the policy is applied, the account stays in `TrustNotEstablished`. Save the policy from `get --output json` to a file and apply it to the role.

On the account side, with the profile of whoever administers it:

```bash
platform cloud account get demo-aws \
  --output json \
  | jq .trustPolicy > /tmp/trust.json

aws iam update-assume-role-policy \
  --role-name platform \
  --policy-document file:///tmp/trust.json \
  --profile <account-admin>
```
