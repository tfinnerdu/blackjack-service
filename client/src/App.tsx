import { BrowserRouter, Route, Routes } from "react-router-dom";

import Home from "./pages/Home";
import JoinRoom from "./pages/JoinRoom";
import Play from "./pages/Play";
import Poker from "./pages/Poker";
import PokerSetup from "./pages/PokerSetup";
import PokerTable from "./pages/PokerTable";
import Setup from "./pages/Setup";
import Stats from "./pages/Stats";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/setup" element={<Setup />} />
        <Route path="/play" element={<Play />} />
        <Route path="/stats" element={<Stats />} />
        <Route path="/join" element={<JoinRoom />} />
        <Route path="/join/:code" element={<JoinRoom />} />
        <Route path="/poker" element={<Poker />} />
        <Route path="/poker/sim/setup" element={<PokerSetup />} />
        <Route path="/poker/sim/table" element={<PokerTable />} />
      </Routes>
    </BrowserRouter>
  );
}
