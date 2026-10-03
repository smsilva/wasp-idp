// Entity page header: the stock EntityHeaderBui (@backstage/plugin-catalog,
// src/alpha/components/EntityHeader) plus Source/Docs metadata items built from
// the entity-icon-link extensions that used to live in the About card. A custom
// header layout only receives tabs, so it also renders the context menu itself.
// Review against EntityHeaderBui when upgrading Backstage.
import { ReactElement, ReactNode, useMemo } from 'react';
import { useRouteRefParams } from '@backstage/core-plugin-api';
import {
  ExtensionBoundary,
  type AppNode,
} from '@backstage/frontend-plugin-api';
import {
  entityRouteRef,
  getEntityRelations,
  useAsyncEntity,
  useEntityPresentation,
  useEntityRefLink,
  useStarredEntity,
} from '@backstage/plugin-catalog-react';
import type {
  EntityContextMenuItemData,
  EntityHeaderLayoutProps,
} from '@backstage/plugin-catalog-react/alpha';
import {
  Box,
  ButtonIcon,
  Header,
  HeaderMetadataUsers,
  Link,
  Menu,
  MenuItem,
  MenuTrigger,
} from '@backstage/ui';
import type { IconLinkVerticalProps } from '@backstage/core-components';
import StarIcon from '@material-ui/icons/Star';
import StarBorderIcon from '@material-ui/icons/StarBorder';
import MoreVertIcon from '@material-ui/icons/MoreVert';
import { useOwnerUsers } from './useOwnerUsers';

type Entity = NonNullable<ReturnType<typeof useAsyncEntity>['entity']>;
type EntityRef = ReturnType<typeof getEntityRelations>[number];

export type HeaderIconLink = {
  id: string;
  filter: (entity: Entity) => boolean;
  useProps: () => IconLinkVerticalProps;
};

export type HeaderMenuItem = {
  node: AppNode;
  data: EntityContextMenuItemData;
  filter: (entity: Entity) => boolean;
};

// Metadata label and link text per icon link; anything else falls back to the
// link's own label
const iconLinkPresentation: Record<
  string,
  { label: string; text: (href: string) => string }
> = {
  'entity-icon-link:catalog/view-source': {
    label: 'Source',
    // https://github.com/<org>/<repo>/... -> <repo>
    text: href => new URL(href).pathname.split('/')[2] || 'Source',
  },
  'entity-icon-link:techdocs/read-docs': {
    label: 'Docs',
    text: () => 'TechDocs',
  },
};

const refName = (ref: EntityRef) =>
  `${ref.kind}:${ref.namespace}/${ref.name}`.toLocaleLowerCase('en-US');

function HierarchyLinks({ refs }: { refs: EntityRef[] }) {
  const entityLink = useEntityRefLink();
  return (
    <>
      {refs.map((ref, index) => (
        <span key={refName(ref)}>
          {index > 0 ? ', ' : null}
          <Link href={entityLink(ref)} standalone>
            {ref.name}
          </Link>
        </span>
      ))}
    </>
  );
}

function hierarchyLabel(ref: EntityRef) {
  switch (ref.kind.toLocaleLowerCase('en-US')) {
    case 'system':
      return 'System';
    case 'domain':
      return 'Domain';
    default:
      return 'Part of';
  }
}

function IconLinkValue({
  href,
  icon,
  text,
}: {
  href: string;
  icon: ReactNode;
  text: string;
}) {
  const external = /^https?:\/\//.test(href);
  return (
    <Link
      href={href}
      standalone
      target={external ? '_blank' : undefined}
      rel={external ? 'noopener noreferrer' : undefined}
    >
      <Box
        as="span"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
      >
        <Box as="span" style={{ display: 'inline-flex', fontSize: 16 }}>
          {icon}
        </Box>
        {text}
      </Box>
    </Link>
  );
}

function useMetadata(entity: Entity | undefined, iconLinks: HeaderIconLink[]) {
  const owners = useOwnerUsers(entity);
  // Hook count is stable: iconLinks comes from the extension inputs, fixed for
  // the lifetime of the app.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const linkProps = iconLinks.map(link => ({ link, props: link.useProps() }));

  return useMemo(() => {
    if (!entity) return [];
    const metadata: { label: string; value: ReactNode }[] = [];

    const lifecycle = (entity.spec as { lifecycle?: unknown })?.lifecycle;
    if (lifecycle) {
      metadata.push({ label: 'Lifecycle', value: String(lifecycle) });
    }
    if (owners.length > 0) {
      metadata.push({
        label: 'Owner',
        value: <HeaderMetadataUsers users={owners} />,
      });
    }
    const hierarchy = getEntityRelations(entity, 'partOf').reduce<
      Record<string, EntityRef[]>
    >((groups, ref) => {
      const label = hierarchyLabel(ref);
      groups[label] = [...(groups[label] ?? []), ref];
      return groups;
    }, {});
    for (const [label, refs] of Object.entries(hierarchy)) {
      metadata.push({ label, value: <HierarchyLinks refs={refs} /> });
    }

    for (const { link, props } of linkProps) {
      if (!link.filter(entity) || props.disabled || !props.href) continue;
      const presentation = iconLinkPresentation[link.id];
      metadata.push({
        label: presentation?.label ?? props.label,
        value: (
          <IconLinkValue
            href={props.href}
            icon={props.icon}
            text={presentation?.text(props.href) ?? props.label}
          />
        ),
      });
    }
    return metadata;
    // linkProps is rebuilt every render; its content only changes with entity
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entity, owners]);
}

function FavoriteEntityButton({ entity }: { entity: Entity }) {
  const { isStarredEntity, toggleStarredEntity } = useStarredEntity(entity);
  return (
    <ButtonIcon
      variant="secondary"
      aria-label={
        isStarredEntity ? 'Remove from favorites' : 'Add to favorites'
      }
      icon={
        isStarredEntity ? (
          <StarIcon style={{ fontSize: 18 }} />
        ) : (
          <StarBorderIcon style={{ fontSize: 18 }} />
        )
      }
      onPress={() => toggleStarredEntity()}
    />
  );
}

function ContextMenuItemContent({ data }: { data: EntityContextMenuItemData }) {
  const { icon, useProps } = data;
  const { title, disabled, onClick, ...rest } = useProps();
  const onAction = onClick
    ? () => {
        const result = onClick();
        if (result) {
          void result.catch(() => {});
        }
      }
    : undefined;
  return (
    <MenuItem
      iconStart={icon as ReactElement}
      href={'href' in rest ? rest.href : undefined}
      onAction={onAction}
      isDisabled={disabled}
    >
      {title}
    </MenuItem>
  );
}

function EntityContextMenu({ items }: { items: HeaderMenuItem[] }) {
  if (items.length === 0) return null;
  return (
    <MenuTrigger>
      <ButtonIcon
        variant="secondary"
        icon={<MoreVertIcon style={{ fontSize: 18 }} />}
        aria-label="More"
      />
      <Menu placement="bottom end">
        {items.map(item => (
          <ExtensionBoundary
            key={item.node.spec.id}
            node={item.node}
            errorPresentation="error-api"
          >
            <ContextMenuItemContent data={item.data} />
          </ExtensionBoundary>
        ))}
      </Menu>
    </MenuTrigger>
  );
}

export function createEntityHeader(
  iconLinks: HeaderIconLink[],
  menuItems: HeaderMenuItem[],
) {
  return function EntityHeader(props: EntityHeaderLayoutProps) {
    const { entity } = useAsyncEntity();
    const routeParams = useRouteRefParams(entityRouteRef);
    const presentation = useEntityPresentation(entity ?? routeParams);
    const metadata = useMetadata(entity, iconLinks);
    const type = (entity?.spec as { type?: unknown } | undefined)?.type;

    return (
      <Header
        title={presentation.primaryTitle}
        tags={[
          { label: entity?.kind ?? routeParams.kind },
          ...(type ? [{ label: String(type) }] : []),
        ]}
        metadata={metadata}
        tabs={entity ? props.tabs : undefined}
        activeTabId={props.activeTabId}
        customActions={
          entity ? (
            <>
              <FavoriteEntityButton entity={entity} />
              <EntityContextMenu
                items={menuItems.filter(item => item.filter(entity))}
              />
            </>
          ) : undefined
        }
      />
    );
  };
}
