import React from "react";
import { useTheme } from "./state/themeState";
import TopBar from "./layouts/TopBar";
import Navigation from "./layouts/Navigation";
import ThematicTheater from "./layouts/ThematicTheater";
import RightDrawer from "./layouts/RightDrawer";
import tokensCSS from "./tokens.css";

const App: React.FC = () => {
  const { theme, setTheme } = useTheme();

  return (
    <div className="aeon-workspace" style={{ theme }}>
      <TopBar setTheme={setTheme} />
      <Navigation />
      <ThematicTheater />
      <RightDrawer />
    </div>
  );
};

export default App;