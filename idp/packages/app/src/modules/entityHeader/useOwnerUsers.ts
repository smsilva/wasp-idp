import { useEffect, useMemo, useState } from 'react';
import { useApi } from '@backstage/core-plugin-api';
import {
  catalogApiRef,
  getEntityRelations,
  useAsyncEntity,
  useEntityRefLink,
} from '@backstage/plugin-catalog-react';

type Entity = NonNullable<ReturnType<typeof useAsyncEntity>['entity']>;

// Owners as HeaderMetadataUsers expects them (name, avatar, link), same lookup
// as the stock EntityHeaderBui
export function useOwnerUsers(entity: Entity | undefined) {
  const catalogApi = useApi(catalogApiRef);
  const entityLink = useEntityRefLink();
  const ownerRefs = useMemo(
    () => (entity ? getEntityRelations(entity, 'ownedBy') : []),
    [entity],
  );
  const ownerRefStrings = useMemo(
    () =>
      ownerRefs.map(ref =>
        `${ref.kind}:${ref.namespace}/${ref.name}`.toLocaleLowerCase('en-US'),
      ),
    [ownerRefs],
  );
  const [ownerEntities, setOwnerEntities] = useState<
    Awaited<ReturnType<typeof catalogApi.getEntitiesByRefs>>['items']
  >([]);
  useEffect(() => {
    if (ownerRefStrings.length === 0) return undefined;
    let cancelled = false;
    catalogApi
      .getEntitiesByRefs({
        entityRefs: ownerRefStrings,
        fields: [
          'kind',
          'metadata.name',
          'metadata.namespace',
          'metadata.title',
          'spec.profile',
        ],
      })
      .then(({ items }) => {
        if (!cancelled) setOwnerEntities(items);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [catalogApi, ownerRefStrings]);

  return ownerRefs.map((ref, index) => {
    const owner = ownerEntities?.[index];
    const profile = owner?.spec?.profile as { picture?: string } | undefined;
    return {
      name: owner?.metadata.title ?? owner?.metadata.name ?? ref.name,
      src: profile?.picture,
      href: entityLink(ref),
    };
  });
}
