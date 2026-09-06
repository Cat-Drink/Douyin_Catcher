import { FloatingDock } from "../components/app/FloatingDock";
import { TitleBar } from "../components/app/TitleBar";
import { SlidePanel } from "../components/app/SlidePanel";
import SettingsPanel from "../components/app/SettingsPanel";
import CookiePanel from "../components/app/CookiePanel";
import { Outlet, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { usePanelStore } from "../store/panelStore";
import { pageVariants, pageTransition } from "../lib/motion";

export function AppShell() {
  const { activePanel, closePanel } = usePanelStore();
  const location = useLocation();

  return (
    <div className="flex flex-col h-full w-full bg-bg-base overflow-hidden transition-colors">
      <TitleBar />
      <div className="relative flex-1 overflow-hidden">
        {/* 悬浮球/感应式抽屉导航（替代传统侧边栏） */}
        <FloatingDock />
        {/* 路由切换弹性过渡：opacity 0->1 + y 12->0 */}
        <AnimatePresence mode="wait" initial={false}>
          <motion.main
            key={location.pathname}
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={pageTransition}
            className="h-full flex flex-col overflow-hidden pl-16"
          >
            <Outlet />
          </motion.main>
        </AnimatePresence>
      </div>

      {/* 侧滑面板 */}
      <SlidePanel
        open={activePanel === "settings"}
        title="设置"
        onClose={closePanel}
      >
        <SettingsPanel />
      </SlidePanel>
      <SlidePanel
        open={activePanel === "cookie"}
        title="Cookie 配置"
        onClose={closePanel}
      >
        <CookiePanel />
      </SlidePanel>
    </div>
  );
}
