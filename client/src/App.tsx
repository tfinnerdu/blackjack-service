import { BrowserRouter, Route, Routes } from "react-router-dom";

import Home from "./pages/Home";
import Play from "./pages/Play";
import Setup from "./pages/Setup";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/setup" element={<Setup />} />
        <Route path="/play" element={<Play />} />
      </Routes>
    </BrowserRouter>
  );
}
