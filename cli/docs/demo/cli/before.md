# Before the demo

Run these before the meeting. The demo needs the SCM connection, the registry and the catalog in place:

```bash
platform status
```

You are in `team-alpha`, the owner of the app:

```bash
platform whoami
```

The system `greeter`, which the app joins, is in the catalog:

```bash
platform catalog system get greeter
```

The repo does not exist yet. A repo left by an earlier run stops the create ([After the demo](cleanup.md)), so `Could not resolve to a Repository` is the expected answer:

```bash
gh repo view wasp-foundry/hello-api
```

The SSH alias that [Clone the app](clone.md) sets up answers with an account that is a member of `wasp-foundry`:

```bash
ssh -T git@github.com-personal
```
