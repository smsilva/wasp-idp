# Control plane

```bash
time platform init \
  --target local \
  --admin you@example.com
```

``` { .text .output title="output" }
▶ cluster
▶ build images
✓ build images  2.3s
✓ cluster  39.1s
▶ CRDs
▶ import images
importing 6 image(s) into platform-local …
✓ CRDs  3.8s
▶ keycloak
▶ traefik
▶ pod policy
▶ shared-pg
▶ templates
▶ prometheus
▶ profile policies
registering 1 template(s) at f000824 …
✓ profile policies  0.3s
✓ pod policy  0.4s
✓ templates  1.4s
✓ prometheus  13.9s
✓ shared-pg  22.1s
✓ traefik  1m40s
✓ import images  1m57s
▶ workload-provider
▶ local-vcluster-provider
▶ forager-provider
▶ aws-account-provider
▶ scm-github-provider
▶ registry-provider
✓ aws-account-provider  0.6s
✓ scm-github-provider  3.4s
✓ forager-provider  3.4s
✓ registry-provider  3.4s
✓ local-vcluster-provider  3.5s
✓ workload-provider  3.5s
✓ keycloak  2m00s
▶ keycloak realm
✓ keycloak realm  31.4s
▶ keycloak admin permissions
enabling fine-grained admin permissions …
✓ keycloak admin permissions  1.0s
▶ platform-api
✓ platform-api  17.0s

timings:
  build images                 2.3s
  cluster                     39.1s
  CRDs                         3.8s
  profile policies             0.3s
  pod policy                   0.4s
  templates                    1.4s
  prometheus                  13.9s
  shared-pg                   22.1s
  traefik                     1m40s
  import images               1m57s
  aws-account-provider         0.6s
  scm-github-provider          3.4s
  forager-provider             3.4s
  registry-provider            3.4s
  local-vcluster-provider      3.5s
  workload-provider            3.5s
  keycloak                    2m00s
  keycloak realm              31.4s
  keycloak admin permissions   1.0s
  platform-api                17.0s
  total                       3m32s
✓ Platform API at http://127.0.0.1:9090 · config in ~/.config/platform/config.yaml
✓ Keycloak issuer http://localhost:8180/realms/platform

real    3m33s
```
