import React from "react";
import { useTheme } from "../state/themeState";
import { FlowCanvas } from "../components/FlowCanvas";
import { AGGridConsole } from "../components/AGGridConsole";

const ThematicTheater: React.FC = () => {
  const { theme } = useTheme();

  return (
    <main className="main-operation-theater" style={{ theme }}>
      <section className="topology-canvas-pane" id="react-flow-canvas">
        <FlowCanvas />
      </section>
      <section className="data-grid-tabs-pane" id="ag-grid-console">
        <AGGridConsole />
      </section>
    </main>
  );
};

export default ThematicTheater;