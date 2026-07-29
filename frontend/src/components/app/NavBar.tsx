import { useLocation, useNavigate } from "react-router-dom";
import { cn } from "../../lib/utils";
import { mockNavItems } from "../../data/mock";
import { Download, Link, User, Key, Settings } from "lucide-react";

const iconMap: Record<string, React.ReactNode> = {
  download: <Download size={20} />,
  link: <Link size={20} />,
  user: <User size={20} />,
  key: <Key size={20} />,
  settings: <Settings size={20} />,
};

export function NavBar() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <nav className="flex flex-col w-[200px] min-w-[200px] h-full bg-white border-r border-border-light">
      {/* Logo */}
      <div className="flex items-center gap-2 h-16 px-5">
        <div className="w-8 h-8 rounded-lg bg-purple-500 flex items-center justify-center text-white text-sm font-bold">
          撷
        </div>
        <span className="text-base font-semibold text-purple-500">撷风拾影</span>
      </div>

      {/* Nav Items */}
      <div className="flex-1 flex flex-col gap-0.5 px-2">
        {mockNavItems.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <button
              key={item.id}
              onClick={() => navigate(item.path)}
              className={cn(
                "flex items-center gap-3 h-11 px-4 rounded-sm text-sm transition-colors",
                "border-l-3 border-transparent",
                isActive
                  ? "bg-bg-selected text-purple-500 font-medium border-l-purple-500"
                  : "text-text-secondary hover:bg-bg-hover hover:text-text-primary",
              )}
            >
              <span className={cn(isActive ? "text-purple-500" : "text-text-secondary")}>
                {iconMap[item.icon]}
              </span>
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      {/* Status Bar */}
      <div className="border-t border-border-light px-5 py-3">
        <div className="flex items-center justify-between text-xs text-text-disabled">
          <span>v0.2.3</span>
        </div>
      </div>
    </nav>
  );
}