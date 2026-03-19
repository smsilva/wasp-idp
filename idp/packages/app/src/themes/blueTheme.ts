import {
  createUnifiedTheme,
  genPageTheme,
  palettes,
  shapes,
  UnifiedThemeProvider,
} from '@backstage/theme';
import { ThemeBlueprint } from '@backstage/plugin-app-react';
import { createFrontendModule } from '@backstage/frontend-plugin-api';
import React from 'react';

const blueLight = createUnifiedTheme({
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

const blueDark = createUnifiedTheme({
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
  pageTheme: {
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
  },
});

const blueLightExtension = ThemeBlueprint.make({
  name: 'blue-light',
  params: {
    theme: {
      id: 'blue-light',
      title: 'Blue Light',
      variant: 'light',
      Provider: ({ children }) =>
        React.createElement(UnifiedThemeProvider, { theme: blueLight, children }),
    },
  },
});

const blueDarkExtension = ThemeBlueprint.make({
  name: 'blue-dark',
  params: {
    theme: {
      id: 'blue-dark',
      title: 'Blue Dark',
      variant: 'dark',
      Provider: ({ children }) =>
        React.createElement(UnifiedThemeProvider, { theme: blueDark, children }),
    },
  },
});

export const blueThemeModule = createFrontendModule({
  pluginId: 'app',
  extensions: [blueLightExtension, blueDarkExtension],
});
