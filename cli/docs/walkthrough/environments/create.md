# Create an environment

```bash
time platform environment create greetings-test \
  --profile ephemeral \
  --expires 1h \
  --wait
```

``` { .text .output title="output" }
provisioning greetings-test (profile: ephemeral) …
  NoProviderForCapability
  Provisioning
✓ greetings-test ready

real    0m32s
```

!!! note
    The request starts at `NoProviderForCapability` and the `local_vcluster` provider, which runs inside `platform-local`, picks it up right after. **There is no second terminal.**
