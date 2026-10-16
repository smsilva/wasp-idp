# Get ready

Run these before the meeting. The demo needs the SCM connection, the registry and the catalog in place:

```bash
platform status
```

Who you are:

```bash
platform whoami
```

The system `seat-map`, which the app joins, is in the catalog, owned by `team-airport`, the owner of the app:

```bash
platform catalog system get seat-map
```

The repo does not exist yet. A repo left by an earlier run stops the create, and `scripts/demo/cleanup` removes it ([Wrap up](cleanup.md)), so `Could not resolve to a Repository` is the expected answer:

```bash
gh repo view wasp-foundry/seat-selection
```

The SSH alias that [Clone the app](clone.md) sets up answers with an account that is a member of `wasp-foundry`:

```bash
ssh -T git@github.com-personal
```
