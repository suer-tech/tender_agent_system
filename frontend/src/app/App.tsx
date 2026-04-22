import React from 'react';
import { RouterProvider } from 'react-router';
import { ThemeProvider } from 'next-themes';
import { router } from './routes';
import { AppStateProvider } from './store';

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <AppStateProvider>
        <RouterProvider router={router} />
      </AppStateProvider>
    </ThemeProvider>
  );
}

export default App;
