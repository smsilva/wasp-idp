# Control plane

`PLATFORM_ADMIN_EMAIL` holds your Google e-mail: that account becomes the platform admin.

```bash
time platform init \
  --target local \
  --admin "${PLATFORM_ADMIN_EMAIL:-email_not_filled}"
```
