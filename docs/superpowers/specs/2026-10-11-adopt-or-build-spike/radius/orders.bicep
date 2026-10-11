extension radius

@description('The ID of your Radius Environment. Set automatically by the rad CLI.')
param environment string

@secure()
param password string

resource app 'Radius.Core/applications@2025-08-01-preview' = {
  name: 'orders'
  properties: {
    environment: environment
  }
}

resource dbCreds 'Radius.Security/secrets@2025-08-01-preview' = {
  name: 'orders-db-client'
  properties: {
    environment: environment
    application: app.id
    data: {
      password: {
        value: password
      }
    }
  }
}

resource db 'Radius.Data/postgreSqlDatabases@2025-08-01-preview' = {
  name: 'db'
  properties: {
    environment: environment
    application: app.id
    database: 'orders'
    username: 'orders'
    password: password
    tls: 'optional'
  }
}

resource orders 'Radius.Compute/containers@2025-08-01-preview' = {
  name: 'orders'
  properties: {
    environment: environment
    application: app.id
    containers: {
      api: {
        image: 'postgres:17-alpine'
        command: ['sh', '-c']
        args: ['export PGHOST=$CONNECTION_DB_HOST PGPORT=$CONNECTION_DB_PORT PGDATABASE=$CONNECTION_DB_DATABASE PGUSER=$CONNECTION_DB_USERNAME PGPASSWORD=$CONNECTION_DB_PASSWORD; env | grep ^CONNECTION_DB_ | cut -d= -f1; until psql -c "select current_database(), current_user"; do sleep 2; done; sleep infinity']
        env: {
          CONNECTION_DB_PASSWORD: {
            valueFrom: {
              secretKeyRef: {
                secretName: dbCreds.name
                key: 'password'
              }
            }
          }
        }
      }
    }
    connections: {
      db: {
        source: db.id
      }
    }
  }
}
