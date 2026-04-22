import React from 'react';
import { Outlet } from 'react-router';
import { ToastContainer } from '../components/ToastContainer';

export const RootLayout: React.FC = () => {
  return (
    <>
      <Outlet />
      <ToastContainer />
    </>
  );
};
