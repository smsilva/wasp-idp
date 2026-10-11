# Remove

Removing deletes the connection and the key. The App **remains on GitHub**, and the output says where to delete it:

```bash
platform scm connection remove wasp-foundry
```

``` { .text .output title="output" }
✓ connection wasp-foundry removed, with its private key
  the GitHub App still exists; an org owner deletes it at https://github.com/organizations/wasp-foundry/settings/apps/wasp-foundry-platform (Advanced → Delete GitHub App)
```
