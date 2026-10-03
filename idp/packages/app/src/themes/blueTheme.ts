import {
  createUnifiedTheme,
  genPageTheme,
  palettes,
  shapes,
  UnifiedTheme,
  UnifiedThemeOptions,
  UnifiedThemeProvider,
} from '@backstage/theme';
import { ThemeBlueprint } from '@backstage/plugin-app-react';
import { createFrontendModule } from '@backstage/frontend-plugin-api';
import React from 'react';

// Compact type scale shared by every theme. The @backstage/theme defaults
// (h4 28px, h5 24px, body1 16px) dwarf the ~14px table rows; here body text,
// inputs and tables are all 14px and headings only step up a little.
const compactTypography: Pick<
  UnifiedThemeOptions,
  'typography' | 'components'
> = {
  typography: {
    htmlFontSize: 16,
    fontFamily: '"Helvetica Neue", Helvetica, Roboto, Arial, sans-serif',
    h1: { fontSize: 32, fontWeight: 700, marginBottom: 10 },
    h2: { fontSize: 26, fontWeight: 700, marginBottom: 8 },
    h3: { fontSize: 22, fontWeight: 700, marginBottom: 6 },
    h4: { fontSize: 20, fontWeight: 700, marginBottom: 6 },
    h5: { fontSize: 18, fontWeight: 700, marginBottom: 4 },
    h6: { fontSize: 16, fontWeight: 700, marginBottom: 2 },
  },
  components: {
    MuiTypography: {
      styleOverrides: { body1: { fontSize: 14 } },
    },
    MuiInputBase: {
      styleOverrides: { root: { fontSize: 14 } },
    },
  },
};

const blueLight = createUnifiedTheme({
  ...compactTypography,
  palette: {
    ...palettes.light,
    primary: {
      main: '#1565C0',
      dark: '#0D47A1',
      light: '#1976D2',
    },
    secondary: {
      main: '#0288D1',
    },
    navigation: {
      background: '#0A1929',
      indicator: '#5C9CE6',
      color: '#B2DFFC',
      selectedColor: '#FFFFFF',
      navItem: {
        hoverBackground: '#132F4C',
      },
      submenu: {
        background: '#071423',
      },
    },
  },
  defaultPageTheme: 'home',
  pageTheme: {
    home: genPageTheme({ colors: ['#1565C0', '#0D47A1'], shape: shapes.wave }),
    documentation: genPageTheme({
      colors: ['#0288D1', '#01579B'],
      shape: shapes.wave2,
    }),
    tool: genPageTheme({ colors: ['#1E88E5', '#1565C0'], shape: shapes.round }),
    service: genPageTheme({
      colors: ['#1976D2', '#0D47A1'],
      shape: shapes.wave,
    }),
    website: genPageTheme({
      colors: ['#0288D1', '#1565C0'],
      shape: shapes.wave,
    }),
    library: genPageTheme({
      colors: ['#42A5F5', '#1565C0'],
      shape: shapes.wave2,
    }),
    other: genPageTheme({ colors: ['#1565C0', '#01579B'], shape: shapes.wave }),
    app: genPageTheme({ colors: ['#1976D2', '#0D47A1'], shape: shapes.wave }),
    apis: genPageTheme({ colors: ['#0288D1', '#1565C0'], shape: shapes.wave }),
  },
});

const darkPageTheme = {
  home: genPageTheme({ colors: ['#0D47A1', '#1565C0'], shape: shapes.wave }),
  documentation: genPageTheme({
    colors: ['#01579B', '#0288D1'],
    shape: shapes.wave2,
  }),
  tool: genPageTheme({ colors: ['#1565C0', '#1E88E5'], shape: shapes.round }),
  service: genPageTheme({
    colors: ['#0D47A1', '#1976D2'],
    shape: shapes.wave,
  }),
  website: genPageTheme({
    colors: ['#1565C0', '#0288D1'],
    shape: shapes.wave,
  }),
  library: genPageTheme({
    colors: ['#1565C0', '#42A5F5'],
    shape: shapes.wave2,
  }),
  other: genPageTheme({ colors: ['#01579B', '#1565C0'], shape: shapes.wave }),
  app: genPageTheme({ colors: ['#0D47A1', '#1976D2'], shape: shapes.wave }),
  apis: genPageTheme({ colors: ['#1565C0', '#0288D1'], shape: shapes.wave }),
};

const blueDark = createUnifiedTheme({
  ...compactTypography,
  palette: {
    ...palettes.dark,
    primary: {
      main: '#42A5F5',
      dark: '#1E88E5',
      light: '#90CAF9',
    },
    secondary: {
      main: '#40C4FF',
    },
    navigation: {
      background: '#071423',
      indicator: '#42A5F5',
      color: '#B2DFFC',
      selectedColor: '#FFFFFF',
      navItem: {
        hoverBackground: '#0A1929',
      },
      submenu: {
        background: '#040D17',
      },
    },
  },
  defaultPageTheme: 'home',
  pageTheme: darkPageTheme,
});

// Neutral grey, GitHub-dark style: more contrast between page and cards.
const graphiteDark = createUnifiedTheme({
  ...compactTypography,
  palette: {
    ...palettes.dark,
    background: { default: '#0D1117', paper: '#161B22' },
    divider: '#30363D',
    primary: { main: '#58A6FF', dark: '#1F6FEB', light: '#79C0FF' },
    secondary: { main: '#A371F7' },
    navigation: {
      background: '#010409',
      indicator: '#58A6FF',
      color: '#8B949E',
      selectedColor: '#F0F6FC',
      navItem: { hoverBackground: '#161B22' },
      submenu: { background: '#0D1117' },
    },
  },
  defaultPageTheme: 'home',
  pageTheme: darkPageTheme,
});

// Near-black page with navy cards and a cyan accent: the current blue identity, darker.
const midnightDark = createUnifiedTheme({
  ...compactTypography,
  palette: {
    ...palettes.dark,
    background: { default: '#05070D', paper: '#0B1A2E' },
    divider: '#16314F',
    primary: { main: '#22D3EE', dark: '#0891B2', light: '#67E8F9' },
    secondary: { main: '#38BDF8' },
    navigation: {
      background: '#020409',
      indicator: '#22D3EE',
      color: '#94C5E8',
      selectedColor: '#FFFFFF',
      navItem: { hoverBackground: '#0B1A2E' },
      submenu: { background: '#05070D' },
    },
  },
  defaultPageTheme: 'home',
  pageTheme: darkPageTheme,
});

const themeExtension = (
  id: string,
  title: string,
  variant: 'light' | 'dark',
  theme: UnifiedTheme,
) =>
  ThemeBlueprint.make({
    name: id,
    params: {
      theme: {
        id,
        title,
        variant,
        Provider: ({ children }) =>
          React.createElement(UnifiedThemeProvider, {
            theme,
            themeName: id,
            children,
          }),
      },
    },
  });

export const blueThemeModule = createFrontendModule({
  pluginId: 'app',
  extensions: [
    themeExtension('blue-light', 'Blue Light', 'light', blueLight),
    themeExtension('blue-dark', 'Blue Dark', 'dark', blueDark),
    themeExtension('graphite-dark', 'Graphite', 'dark', graphiteDark),
    themeExtension('midnight-dark', 'Midnight', 'dark', midnightDark),
  ],
});
