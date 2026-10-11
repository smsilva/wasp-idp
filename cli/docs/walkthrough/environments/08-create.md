# Create an environment

```bash
time platform environment create greetings-test \
  --profile ephemeral \
  --expires 1h \
  --wait
```

``` { .text .output title="saída" }
provisioning greetings-test (profile: ephemeral) …
  NoProviderForCapability
  Provisioning
✓ greetings-test ready

real    0m32s
```

!!! note
    O pedido começa em `NoProviderForCapability` e o provider `local_vcluster`, que roda dentro do `platform-local`, o assume em seguida. **Não há segundo terminal.**
