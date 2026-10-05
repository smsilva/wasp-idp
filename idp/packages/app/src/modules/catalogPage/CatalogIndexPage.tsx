// Catalog index page without the BUI page header (#128): the header only held
// the "My Company Catalog" title, which repeats the Catalog breadcrumb, and
// the Create button, which now sits in the table toolbar next to the search.
// Everything else is the stock catalog: EntityListProvider, the filter column
// layout (filled by catalog-filter extensions) and CatalogTable.
import { ReactNode } from 'react';
import { useRouteRef } from '@backstage/frontend-plugin-api';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import { CatalogTable } from '@backstage/plugin-catalog';
import {
  CatalogFilterLayout,
  EntityListPagination,
  EntityListProvider,
} from '@backstage/plugin-catalog-react';
import { catalogEntityCreatePermission } from '@backstage/plugin-catalog-common/alpha';
import { usePermission } from '@backstage/plugin-permission-react';
import { ButtonLink, Container } from '@backstage/ui';
import { LuPlus } from 'react-icons/lu';
import styles from './CatalogIndexPage.module.css';

function CreateButton() {
  const createComponentLink = useRouteRef(
    catalogPlugin.externalRoutes.createComponent,
  );
  const { allowed } = usePermission({
    permission: catalogEntityCreatePermission,
  });
  const href = createComponentLink?.();
  if (!allowed || !href) return null;
  return (
    <ButtonLink
      className={styles.create}
      variant="primary"
      size="small"
      href={href}
      iconStart={<LuPlus aria-hidden />}
    >
      Create
    </ButtonLink>
  );
}

export function CatalogIndexPage(props: {
  filters: ReactNode;
  pagination?: EntityListPagination;
}) {
  return (
    <EntityListProvider pagination={props.pagination}>
      <Container className={styles.root}>
        <CatalogFilterLayout>
          <CatalogFilterLayout.Filters>
            {props.filters}
          </CatalogFilterLayout.Filters>
          <CatalogFilterLayout.Content>
            <div className={styles.content}>
              <CatalogTable />
              <CreateButton />
            </div>
          </CatalogFilterLayout.Content>
        </CatalogFilterLayout>
      </Container>
    </EntityListProvider>
  );
}
