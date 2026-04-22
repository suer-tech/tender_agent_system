import { createBrowserRouter } from "react-router";
import { Root } from "./Root";
import { MarketPage } from "./pages/MarketPage";
import { RootLayout } from "./layouts/RootLayout";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: RootLayout,
    children: [
      { index: true, Component: Root },
      { path: "market", Component: MarketPage },
    ],
  },
]);
