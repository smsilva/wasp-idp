import {
  Sidebar,
  SidebarDivider,
  SidebarGroup,
  SidebarItem,
  SidebarScrollWrapper,
  SidebarSpace,
} from '@backstage/core-components';
import ApartmentIcon from '@material-ui/icons/Apartment';
import CatalogIcon from '@material-ui/icons/LibraryBooks';
import CategoryIcon from '@material-ui/icons/Category';
import ExtensionIcon from '@material-ui/icons/Extension';
import MemoryIcon from '@material-ui/icons/Memory';
import StorageIcon from '@material-ui/icons/Storage';
import { compatWrapper } from '@backstage/core-compat-api';
import { NavContentBlueprint } from '@backstage/plugin-app-react';
import { SidebarLogo } from './SidebarLogo';
import MenuIcon from '@material-ui/icons/Menu';
import SearchIcon from '@material-ui/icons/Search';
import { SidebarSearchModal } from '@backstage/plugin-search';
import {
  UserSettingsSignInAvatar,
  Settings as SidebarSettings,
} from '@backstage/plugin-user-settings';
import { NotificationsSidebarItem } from '@backstage/plugin-notifications';

export const SidebarContent = NavContentBlueprint.make({
  params: {
    component: ({ navItems }) => {
      const nav = navItems.withComponent(item => (
        <SidebarItem icon={() => item.icon} to={item.href} text={item.title} />
      ));
      // Skipped items
      nav.take('page:search');
      nav.take('page:user-settings');
      nav.take('page:notifications');
      // Catalog and the API explorer are rendered by hand, followed by one link per
      // entity kind (the catalog list filtered by kind)
      const catalogHref = navItems.take('page:catalog')?.href ?? '/catalog';
      const apiDocsHref = navItems.take('page:api-docs')?.href ?? '/api-docs';
      const byKind = (kind: string) =>
        `${catalogHref}?filters[kind]=${kind}&filters[user]=all`;
      return compatWrapper(
        <Sidebar>
          <SidebarLogo />
          <SidebarGroup label="Search" icon={<SearchIcon />} to="/search">
            <SidebarSearchModal />
          </SidebarGroup>
          <SidebarDivider />
          <SidebarGroup label="Menu" icon={<MenuIcon />}>
            <SidebarItem icon={CatalogIcon} to={catalogHref} text="Catalog" />
            <SidebarDivider />
            <SidebarItem
              icon={ApartmentIcon}
              to={byKind('domain')}
              text="Domains"
            />
            <SidebarItem
              icon={CategoryIcon}
              to={byKind('system')}
              text="Systems"
            />
            <SidebarItem
              icon={MemoryIcon}
              to={byKind('component')}
              text="Components"
            />
            <SidebarItem icon={ExtensionIcon} to={apiDocsHref} text="APIs" />
            <SidebarItem
              icon={StorageIcon}
              to={byKind('resource')}
              text="Resources"
            />
            <SidebarDivider />
            {nav.take('page:scaffolder')}
            <SidebarDivider />
            <SidebarScrollWrapper>
              {nav.rest({ sortBy: 'title' })}
            </SidebarScrollWrapper>
          </SidebarGroup>
          <SidebarSpace />
          <SidebarDivider />
          <NotificationsSidebarItem />
          <SidebarDivider />
          <SidebarGroup
            label="Settings"
            icon={<UserSettingsSignInAvatar />}
            to="/settings"
          >
            <SidebarSettings />
          </SidebarGroup>
        </Sidebar>,
      );
    },
  },
});
