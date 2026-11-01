import { useState } from "react";
import { Login } from "./components/Login";
import { Workbench } from "./features/workbench/Workbench";

const SESSION_KEY = "exodesk.session";

export default function App() {
  const [authenticated, setAuthenticated] = useState(
    () => sessionStorage.getItem(SESSION_KEY) === "active",
  );

  const login = () => {
    sessionStorage.setItem(SESSION_KEY, "active");
    setAuthenticated(true);
  };

  const logout = () => {
    sessionStorage.removeItem(SESSION_KEY);
    setAuthenticated(false);
  };

  return authenticated ? <Workbench onLogout={logout} /> : <Login onLogin={login} />;
}
