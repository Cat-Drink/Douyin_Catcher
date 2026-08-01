import { NavBar } from "../components/NavBar";
import { Outlet } from "react-router-dom";

export function AppShell() {
  return (
    <div className="flex h-screen w-screen bg-bg-base overflow-hidden transition-colors">
      <NavBar />
      <main className="flex-1 flex flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}