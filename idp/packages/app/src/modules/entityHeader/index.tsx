import {
  createExtensionInput,
  createFrontendModule,
} from '@backstage/frontend-plugin-api';
import { useApi, alertApiRef, errorApiRef } from '@backstage/core-plugin-api';
import { catalogApiRef, useEntity } from '@backstage/plugin-catalog-react';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import {
  EntityContextMenuItemBlueprint,
  EntityHeaderLayoutBlueprint,
  EntityIconLinkBlueprint,
} from '@backstage/plugin-catalog-react/alpha';
import EditIcon from '@material-ui/icons/Edit';
import RefreshIcon from '@material-ui/icons/Refresh';
import { createEntityHeader } from './EntityHeader';

// Entity page header (#124, #130): breadcrumb, description, Owner/Lifecycle/
// Source facts and the context menu live in the custom header layout, so the
// About card is disabled and no description card is needed. The wiring of the
// stock extensions (icon links, context menu items, about card) lives in
// app-config.yaml under app.extensions.

const HEADER_ID = 'entity-header-layout:catalog/wasp';

const entityHeaderLayout = EntityHeaderLayoutBlueprint.makeWithOverrides({
  name: 'wasp',
  inputs: {
    iconLinks: createExtensionInput([
      EntityIconLinkBlueprint.dataRefs.useProps,
      EntityIconLinkBlueprint.dataRefs.filterFunction.optional(),
    ]),
    contextMenuItems: createExtensionInput([
      EntityContextMenuItemBlueprint.dataRefs.data,
      EntityContextMenuItemBlueprint.dataRefs.filterFunction.optional(),
    ]),
  },
  factory: (originalFactory, { inputs }) => {
    const iconLinks = inputs.iconLinks.map(link => ({
      id: link.node.spec.id,
      useProps: link.get(EntityIconLinkBlueprint.dataRefs.useProps),
      filter:
        link.get(EntityIconLinkBlueprint.dataRefs.filterFunction) ??
        (() => true),
    }));
    const menuItems = inputs.contextMenuItems.map(item => ({
      node: item.node,
      data: item.get(EntityContextMenuItemBlueprint.dataRefs.data),
      filter:
        item.get(EntityContextMenuItemBlueprint.dataRefs.filterFunction) ??
        (() => true),
    }));
    return originalFactory({
      loader: async () => createEntityHeader(iconLinks, menuItems),
    });
  },
});

const refreshEntityMenuItem = EntityContextMenuItemBlueprint.make({
  name: 'refresh-entity',
  attachTo: { id: HEADER_ID, input: 'contextMenuItems' },
  params: {
    icon: <RefreshIcon style={{ fontSize: 16 }} />,
    useProps: () => {
      const { entity } = useEntity();
      const catalogApi = useApi(catalogApiRef);
      const alertApi = useApi(alertApiRef);
      const errorApi = useApi(errorApiRef);
      const entityRef = `${entity.kind}:${
        entity.metadata.namespace ?? 'default'
      }/${entity.metadata.name}`.toLocaleLowerCase('en-US');
      return {
        title: 'Refresh metadata',
        onClick: async () => {
          try {
            await catalogApi.refreshEntity(entityRef);
            alertApi.post({
              message: 'Refresh scheduled',
              severity: 'info',
              display: 'transient',
            });
          } catch (e) {
            errorApi.post(e as Error);
          }
        },
      };
    },
  },
});

const editEntityMenuItem = EntityContextMenuItemBlueprint.make({
  name: 'edit-entity',
  attachTo: { id: HEADER_ID, input: 'contextMenuItems' },
  params: {
    icon: <EditIcon style={{ fontSize: 16 }} />,
    filter: entity =>
      Boolean(entity.metadata.annotations?.['backstage.io/edit-url']),
    useProps: () => {
      const { entity } = useEntity();
      return {
        title: 'Edit catalog-info.yaml',
        href: entity.metadata.annotations?.['backstage.io/edit-url'] ?? '',
      };
    },
  },
});

// The page layout's own header bar ("Catalog") repeats what the breadcrumb in
// the entity header already shows, so the entity page renders without it.
const entityPageWithoutHeader = catalogPlugin
  .getExtension('page:catalog/entity')
  .override({ params: { noHeader: true } });

export const entityHeaderModule = createFrontendModule({
  pluginId: 'catalog',
  extensions: [
    entityHeaderLayout,
    refreshEntityMenuItem,
    editEntityMenuItem,
    entityPageWithoutHeader,
  ],
});
