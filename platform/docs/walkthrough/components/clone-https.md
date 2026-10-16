# Clone over HTTPS

`clone` uses SSH by default. `--https` clones over HTTPS, and `--directory` picks where:

```bash
platform catalog component clone seat-selection \
  --https \
  --directory /tmp/seat-selection
```

``` { .text .output title="output" }
# git clone https://github.com/wasp-foundry/seat-selection.git /tmp/seat-selection
Cloning into '/tmp/seat-selection'...
```

To make HTTPS the default, add `git_protocol: https` to `~/.config/platform/config.yaml`; `--https` still wins over a `git_protocol: ssh` there.

!!! tip "Several GitHub accounts on one machine"
    Over SSH, git offers your default key. If that key belongs to an account outside the org, the push of [Push a branch](../builds/branch.md) fails with `Permission to wasp-foundry/seat-selection.git denied to <other-user>`. Clone with `--https`, or point the remote at the SSH host alias of the org member's key (a `Host` entry in `~/.ssh/config`): `git -C /tmp/seat-selection remote set-url origin git@<ssh-alias>:wasp-foundry/seat-selection.git`.
