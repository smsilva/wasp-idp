import { SidebarItem, useSidebarPinState } from '@backstage/core-components';
import ChevronLeftIcon from '@material-ui/icons/ChevronLeft';
import ChevronRightIcon from '@material-ui/icons/ChevronRight';

// Same state as the "Pin Sidebar" switch in Settings → Appearance (localStorage
// key sidebarPinState). Unpinned, the sidebar shows icons only and expands on hover.
export const SidebarPinToggle = () => {
  const { isPinned, isMobile, toggleSidebarPinState } = useSidebarPinState();

  if (isMobile) {
    return null;
  }

  return (
    <SidebarItem
      icon={isPinned ? ChevronLeftIcon : ChevronRightIcon}
      text={isPinned ? 'Collapse sidebar' : 'Pin sidebar'}
      onClick={() => toggleSidebarPinState()}
    />
  );
};
