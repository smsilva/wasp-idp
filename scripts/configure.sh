#!/bin/bash

sudo apt-get install postgresql-18

sudo pg_ctlcluster 18 main start

sudo pg_ctlcluster 18 main status

sudo -u postgres psql

ALTER USER postgres PASSWORD 'secret';

\q

export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
export POSTGRES_USER="postgres"
export POSTGRES_PASSWORD="secret"

cd backstage

yarn add --cwd packages/backend pg

code app-config.yaml

backend:
  database:
-    client: better-sqlite3
-    connection: ':memory:'
+    # config options: https://node-postgres.com/api/client
+    client: pg
+    connection:
+      host: ${POSTGRES_HOST}
+      port: ${POSTGRES_PORT}
+      user: ${POSTGRES_USER}
+      password: ${POSTGRES_PASSWORD}
+      # https://node-postgres.com/features/ssl
+      #ssl: require # see https://www.postgresql.org/docs/current/libpq-ssl.html Table 33.1. SSL Mode Descriptions (e.g. require)
+        #ca: # if you have a CA file and want to verify it you can uncomment this section
+        #$file: <file-path>/ca/server.crt

yarn dev

# Backstage override configuration for your local development environment

code app-config.local.yaml

integrations:
  github:
    - host: github.com
      token: ${GITHUB_TOKEN} # this will use the environment variable GITHUB_TOKEN
