import {
  coreServices,
  createBackendModule,
} from '@backstage/backend-plugin-api';
import type { Config } from '@backstage/config';
import {
  kubernetesFetcherExtensionPoint,
  type KubernetesFetcher,
} from '@backstage/plugin-kubernetes-node';

/**
 * Maps cluster name to namespace from the optional `namespace` key of each
 * `kubernetes.clusterLocatorMethods[type=config].clusters[]` entry.
 */
export function readClusterNamespaces(config: Config): Map<string, string> {
  const namespaces = new Map<string, string>();
  const methods =
    config.getOptionalConfigArray('kubernetes.clusterLocatorMethods') ?? [];

  for (const method of methods) {
    if (method.getString('type') !== 'config') {
      continue;
    }
    for (const cluster of method.getOptionalConfigArray('clusters') ?? []) {
      const namespace = cluster.getOptionalString('namespace');
      if (namespace) {
        namespaces.set(cluster.getString('name'), namespace);
      }
    }
  }

  return namespaces;
}

/**
 * Wraps a fetcher so that clusters with a configured namespace are only
 * queried inside it; the default fetcher lists across all namespaces, which a
 * ServiceAccount bound to a single namespace is not allowed to do.
 */
export function scopeFetcherToNamespaces(
  fetcher: KubernetesFetcher,
  namespaces: Map<string, string>,
): KubernetesFetcher {
  return {
    fetchObjectsForService(params) {
      const namespace = namespaces.get(params.clusterDetails.name);
      return fetcher.fetchObjectsForService(
        namespace ? { ...params, namespace } : params,
      );
    },
    fetchPodMetricsByNamespaces(clusterDetails, credential, set, selector) {
      return fetcher.fetchPodMetricsByNamespaces(
        clusterDetails,
        credential,
        set,
        selector,
      );
    },
  };
}

export default createBackendModule({
  pluginId: 'kubernetes',
  moduleId: 'namespace-scoped-fetcher',
  register(reg) {
    reg.registerInit({
      deps: {
        config: coreServices.rootConfig,
        fetchers: kubernetesFetcherExtensionPoint,
      },
      async init({ config, fetchers }) {
        const namespaces = readClusterNamespaces(config);
        if (namespaces.size === 0) {
          return;
        }
        fetchers.addFetcher(async ({ getDefault }) =>
          scopeFetcherToNamespaces(await getDefault(), namespaces),
        );
      },
    });
  },
});
