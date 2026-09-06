import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Download, Link2, User, Monitor, Sparkles, X } from "lucide-react";
import { cn } from "../../lib/utils";
import { dockItemVariants, springDrawer } from "../../lib/motion";

const navItems = [
  { id: "batch-fetch", path: "/batch-fetch", label: "批量抓取", icon: Link2 },
  { id: "profile-fetch", path: "/profile-fetch", label: "主页抓取", icon: User },
  { id: "bili-fetch", path: "/bili-fetch", label: "B站抓取", icon: Monitor },
  { id: "download", path: "/download", label: "下载任务", icon: Download },
];

/**
 * 悬浮微球 / 感应式抽屉导航（Floating Dock）
 * - 收起态：左侧边缘垂直居中的极简图标胶囊列（毛玻璃）
 * - 展开：鼠标贴近左边缘（16px 感应条）或点击主悬浮球，弹性滑出带文字的抽屉
 * - 展开时背景渐晕，移出/点击遮罩后回弹收缩
 * - 动效只走 transform/opacity，保证 GPU 60fps
 */
export function FloatingDock() {
  const location = useLocation();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const edgeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dockRef = useRef<HTMLElement>(null);

  // 鼠标移出 dock（含感应缓冲）后延迟回弹收缩
  const scheduleCollapse = useCallback(() => {
    if (edgeTimer.current) clearTimeout(edgeTimer.current);
    edgeTimer.current = setTimeout(() => setExpanded(false), 350);
  }, []);

  const cancelCollapse = useCallback(() => {
    if (edgeTimer.current) clearTimeout(edgeTimer.current);
  }, []);

  useEffect(() => () => {
    if (edgeTimer.current) clearTimeout(edgeTimer.current);
  }, []);

  const isActive = (path: string) => location.pathname === path;

  return (
    <>
      {/* 展开时的背景渐晕（点击遮罩收起） */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            key="dock-dim"
            className="fixed inset-0 z-30 bg-black/20 dark:bg-black/40"
            style={{ backdropFilter: "blur(1.5px)" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onMouseEnter={scheduleCollapse}
            onClick={() => setExpanded(false)}
          />
        )}
      </AnimatePresence>

      {/* 左侧边缘感应条：贴近即展开 */}
      <div
        className="fixed left-0 top-1/2 -translate-y-1/2 z-30 w-3 h-48"
        onMouseEnter={() => { cancelCollapse(); setExpanded(true); }}
        aria-hidden
      />

      {/* 主悬浮球 / 抽屉容器 */}
      <motion.nav
        ref={dockRef}
        className="fixed left-2 top-1/2 z-40 -translate-y-1/2 glass-surface rounded-2xl overflow-visible select-none"
        initial={false}
        animate={{
          width: expanded ? 176 : 52,
          borderRadius: expanded ? 20 : 26,
          y: "-50%",
        }}
        transition={springDrawer}
        onMouseEnter={() => { cancelCollapse(); setExpanded(true); }}
        onMouseLeave={scheduleCollapse}
        aria-label="主导航"
      >
        <div className="flex flex-col items-stretch gap-1 py-2 px-1.5">
          {/* 主悬浮球：收起态显示 Sparkles，展开态变成收起按钮 */}
          <button
            className="press-feedback flex items-center gap-3 h-9 px-2.5 rounded-xl text-text-secondary hover:text-purple-500"
            onClick={() => setExpanded((v) => !v)}
            title={expanded ? "收起导航" : "展开导航"}
          >
            <motion.span
              animate={{ rotate: expanded ? 90 : 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="flex items-center justify-center w-6 h-6 shrink-0"
            >
              {expanded ? <X size={18} /> : <Sparkles size={18} className="text-purple-500" />}
            </motion.span>
            <AnimatePresence>
              {expanded && (
                <motion.span
                  className="text-xs font-semibold text-text-primary whitespace-nowrap"
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0, transition: { delay: 0.08, duration: 0.2 } }}
                  exit={{ opacity: 0, x: -6, transition: { duration: 0.1 } }}
                >
                  导航
                </motion.span>
              )}
            </AnimatePresence>
          </button>

          <div className="mx-2 h-px bg-border-light shrink-0" />

          {/* 导航项：展开时交错出现（Stagger） */}
          {navItems.map((item, i) => {
            const Icon = item.icon;
            const active = isActive(item.path);
            return (
              <motion.button
                key={item.id}
                custom={i}
                variants={dockItemVariants}
                initial="collapsed"
                animate={expanded ? "expanded" : "collapsed"}
                onClick={() => {
                  navigate(item.path);
                  setExpanded(false);
                }}
                className={cn(
                  "relative flex items-center gap-3 h-9 px-2.5 rounded-xl text-sm whitespace-nowrap",
                  active
                    ? "text-purple-600 dark:text-purple-300 font-medium"
                    : "text-text-secondary hover:text-text-primary",
                )}
                title={item.label}
              >
                {active && (
                  <motion.span
                    layoutId="dock-active-pill"
                    className="absolute inset-0 rounded-xl bg-bg-selected"
                    transition={springDrawer}
                  />
                )}
                <span className="relative flex items-center justify-center w-6 h-6 shrink-0">
                  <Icon size={18} />
                </span>
                <span className="relative">{item.label}</span>
              </motion.button>
            );
          })}
        </div>
      </motion.nav>
    </>
  );
}
