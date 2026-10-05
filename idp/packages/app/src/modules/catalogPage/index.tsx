import {
  coreExtensionData,
  createFrontendModule,
} from '@backstage/frontend-plugin-api';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import { CatalogFilterBlueprint } from '@backstage/plugin-catalog-react/alpha';

// Compact catalog filter column (option A of
// docs/idp/design/catalog-filters/options.html). It replaces every stock
// catalog-filter:catalog/* picker, which are disabled in app-config.yaml.
const catalogFilters = CatalogFilterBlueprint.make({
  name: 'wasp',
  params: {
    loader: async () => {
      const { CatalogFilters } = await import('./CatalogFilters');
      return <CatalogFilters />;
    },
  },
});

// Same page:catalog extension (path, filters input, pagination config), with
// the page body swapped for CatalogIndexPage: no header row, Create in the
// table toolbar.
const catalogIndexPage = catalogPlugin.getExtension('page:catalog').override({
  factory: (originalFactory, { inputs, config }) =>
    originalFactory({
      params: {
        loader: async () => {
          const { CatalogIndexPage } = await import('./CatalogIndexPage');
          const filters = inputs.filters.map((filter, index) => (
            <div key={filter.node.spec.id ?? index}>
              {filter.get(coreExtensionData.reactElement)}
            </div>
          ));
          return (
            <CatalogIndexPage
              filters={filters}
              pagination={config.pagination}
            />
          );
        },
      },
    }),
});

export const catalogPageModule = createFrontendModule({
  pluginId: 'catalog',
  extensions: [catalogFilters, catalogIndexPage],
});
