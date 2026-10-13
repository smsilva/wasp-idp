# Delete the downloaded key

The platform keeps its own copy, in a Secret only the controller reads. The file on your machine is no longer needed (in the example, `wasp-foundry-platform.<date>.private-key.pem`):

```bash
rm ~/Downloads/wasp-foundry-platform.*.private-key.pem
```

The connection is `ready`: go on to [Verify the GitHub connection](../verify.md).
