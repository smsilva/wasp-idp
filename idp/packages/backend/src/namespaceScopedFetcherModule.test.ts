import { ConfigReader } from '@backstage/config';
import type {
  KubernetesFetcher,
  ObjectFetchParams,
} from '@backstage/plugin-kubernetes-node';
import {
  readClusterNamespaces,
  scopeFetcherToNamespaces,
} from './namespaceScopedFetcherModule';

const config = new ConfigReader({
  kubernetes: {
    clusterLocatorMethods: [
      {
        type: 'config',
        clusters: [
          { name: 'development', url: 'https://k', namespace: 'development' },
          { name: 'production', url: 'https://k', namespace: 'production' },
          { name: 'shared', url: 'https://k' },
        ],
      },
      { type: 'localKubectlProxy' },
    ],
  },
});

function paramsFor(cluster: string): ObjectFetchParams {
  return {
    serviceId: 'details',
    clusterDetails: { name: cluster, url: 'https://k', authMetadata: {} },
    credential: { type: 'anonymous' },
    objectTypesToFetch: new Set(),
    customResources: [],
  };
}

describe('namespaceScopedFetcherModule', () => {
  it('reads namespaces only from config clusters that declare one', () => {
    expect(Object.fromEntries(readClusterNamespaces(config))).toEqual({
      development: 'development',
      production: 'production',
    });
  });

  it('returns an empty map without kubernetes config', () => {
    expect(readClusterNamespaces(new ConfigReader({})).size).toBe(0);
  });

  it('forces the configured namespace and passes other clusters through', async () => {
    const inner: KubernetesFetcher = {
      fetchObjectsForService: jest
        .fn()
        .mockResolvedValue({ errors: [], responses: [] }),
      fetchPodMetricsByNamespaces: jest.fn(),
    };
    const fetcher = scopeFetcherToNamespaces(
      inner,
      readClusterNamespaces(config),
    );

    await fetcher.fetchObjectsForService(paramsFor('production'));
    await fetcher.fetchObjectsForService(paramsFor('shared'));

    const calls = (inner.fetchObjectsForService as jest.Mock).mock.calls;
    expect(calls[0][0].namespace).toBe('production');
    expect(calls[1][0].namespace).toBeUndefined();
  });
});
