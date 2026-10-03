import { createFrontendModule } from '@backstage/frontend-plugin-api';
import { SidebarContent } from './Sidebar';

// Start with the sidebar collapsed: core-components treats a missing
// sidebarPinState key as pinned, so seed it only when the user has not chosen yet.
try {
  if (window.localStorage.getItem('sidebarPinState') === null) {
    window.localStorage.setItem('sidebarPinState', 'false');
  }
} catch {
  // localStorage unavailable (private mode, blocked storage): keep the default
}

export const navModule = createFrontendModule({
  pluginId: 'app',
  extensions: [SidebarContent],
});
