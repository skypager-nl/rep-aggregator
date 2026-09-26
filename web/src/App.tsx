import { HashRouter, Route, Routes } from "react-router";
import Layout from "./components/Layout";
import Build from "./pages/Build";
import Captures from "./pages/Captures";
import Compare from "./pages/Compare";
import Explore from "./pages/Explore";
import Factories from "./pages/Factories";
import Factory from "./pages/Factory";
import Home from "./pages/Home";
import Pivot from "./pages/Pivot";
import Reference from "./pages/Reference";
import Tiers from "./pages/Tiers";

// Hash routing: HA ingress can't rewrite deep links to index.html.
export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="tiers" element={<Tiers />} />
          <Route path="ref/:id" element={<Reference />} />
          <Route path="build/:id" element={<Build />} />
          <Route path="factories" element={<Factories />} />
          <Route path="factory/:id" element={<Factory />} />
          <Route path="explore" element={<Explore />} />
          <Route path="pivot" element={<Pivot />} />
          <Route path="compare" element={<Compare />} />
          <Route path="captures" element={<Captures />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
