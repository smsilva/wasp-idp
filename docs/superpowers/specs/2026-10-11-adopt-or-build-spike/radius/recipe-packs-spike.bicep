extension radius

resource compose 'Radius.Core/recipePacks@2025-08-01-preview' = {
  name: 'compose'
  properties: {
    recipes: {
      'Radius.Compute/containers': {
        kind: 'bicep'
        source: 'ghcr.io/radius-project/kube-recipes/containers:latest'
      }
      'Radius.Security/secrets': {
        kind: 'bicep'
        source: 'ghcr.io/radius-project/kube-recipes/secrets:latest'
      }
      'Radius.Data/postgreSqlDatabases': {
        kind: 'terraform'
        source: 'git::https://github.com/smsilva/kargo-spike.git//radius-recipes/compose'
      }
    }
  }
}

resource bind 'Radius.Core/recipePacks@2025-08-01-preview' = {
  name: 'bind'
  properties: {
    recipes: {
      'Radius.Compute/containers': {
        kind: 'bicep'
        source: 'ghcr.io/radius-project/kube-recipes/containers:latest'
      }
      'Radius.Security/secrets': {
        kind: 'bicep'
        source: 'ghcr.io/radius-project/kube-recipes/secrets:latest'
      }
      'Radius.Data/postgreSqlDatabases': {
        kind: 'terraform'
        source: 'git::https://github.com/smsilva/kargo-spike.git//radius-recipes/bind'
      }
    }
  }
}
