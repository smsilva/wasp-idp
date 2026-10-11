# Render

`render` generates locally what `component create` will generate, fetching the content at the registered ref. It is meant for template authors:

```bash
platform catalog template render python-service \
  --name demo \
  --output /tmp/demo \
  --param port=9000

grep 9000 /tmp/demo/Dockerfile

grep template: /tmp/demo/catalog-info.yaml
```

``` { .text .output title="output" }
✓ rendered into /tmp/demo
EXPOSE 9000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
    platform.wasp.silvios.me/template: python-service@0b81690231edcd5920c1f774efc0325c80a4b0a4
```
