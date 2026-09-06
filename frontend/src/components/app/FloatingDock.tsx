import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Download, Link2, User, Monitor, Sparkles, X } from "lucide-react";
import { cn } from "../../lib/utils";

const navItems = [
  { id: "batch-fetch", path: "/batch-fetch", label: "批量抓取", icon: Link2 },
  { id: "profile-fetch", path: "/profile-fetch", label: "主页抓取", icon: User },
  { id: "bili-fetch", path: "/bili-fetch", label: "B站抓取", icon: Monitor },
  { id: "download", path: "/download", label: "下载任务", icon: Download },
];

/** 半圆环展开：半径与角度（右半圆，自上而下 -90° -> 90°） */
const RADIUS = 86;
const ANGLES = [-90, -30, 30, 90];
const arcPos = (deg: number) => ({
  x: Math.round(RADIUS * Math.cos((deg * Math.PI) / 180)),
  y: -Math.round(RADIUS * Math.sin((deg * Math.PI) / 180)),
});

/**
 * 悬浮球 + 半圆环顺序弹出导航（Floating Dock）
 * - 收起态：左侧边缘垂直居中的单颗毛玻璃微球
 * - 展开：鼠标贴近左边缘或点击主球，四个导航图标沿右半圆弧依次弹出（Stagger spring）
 * - 悬浮图标显示文字标签；展开时背景渐晕，移出后回弹收拢
 * - 动效只走 transform/opacity，保证 GPU 60fps
 */
export function FloatingDock() {
  const location = useLocation();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const [hoverLabel, setHoverLabel] = useState<string | null>(null);
  const edgeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleCollapse = useCallback(() => {
    if (edgeTimer.current) clearTimeout(edgeTimer.current);
    edgeTimer.current = setTimeout(() => {
      setExpanded(false);
      setHoverLabel(null);
    }, 350);
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

      {/* 左侧边缘感应条：贴近即展开 */}
      <div
        className="fixed left-0 top-1/2 -translate-y-1/2 z-30 w-3 h-48"
        onMouseEnter={() => { cancelCollapse(); setExpanded(true); }}
        aria-hidden
      />

      {/* 球体 + 圆环区域（负责 hover 保持与移出收缩） */}
      <div
        className="fixed left-6 top-1/2 z-40 select-none"
        style={{ width: 0, height: 0 }}
        onMouseEnter={() => { cancelCollapse(); setExpanded(true); }}
        onMouseLeave={scheduleCollapse}
        aria-label="主导航"
        role="navigation"
      >
        {/* 半圆环导航项：从主球中心沿弧线依次弹出 */}
        {navItems.map((item, i) => {
          const Icon = item.icon;
          const active = isActive(item.path);
          const { x, y } = arcPos(ANGLES[i]);
          return (
            <motion.button
              key={item.id}
              className="absolute flex items-center justify-center rounded-full glass-surface"
              style={{ left: -22, top: -22, width: 44, height: 44 }}
              initial={false}
              animate={
                expanded
                  ? { x, y, scale: 1, opacity: 1 }
                  : { x: 0, y: 0, scale: 0.2, opacity: 0 }
              }
              transition={{
                type: "spring",
                stiffness: 400,
                damping: 24,
                delay: expanded ? 0.05 * i : 0,
              }}
              onClick={() => {
                navigate(item.path);
                setExpanded(false);
              }}
              onMouseEnter={() => setHoverLabel(item.label)}
              onMouseLeave={() => setHoverLabel((v) => (v === item.label ? null : v))}
              title={item.label}
              aria-label={item.label}
            >
              <span
                className={cn(
                  "flex items-center justify-center w-9 h-9 rounded-full transition-colors",
                  active
                    ? "bg-purple-500 text-white shadow-[0_0_16px_rgba(124,58,237,0.45)]"
                    : "text-text-secondary hover:text-purple-500",
                )}
              >
                <Icon size={18} />
              </span>
              {/* 悬浮标签 */}
              {expanded && hoverLabel === item.label && (
                <motion.span
                  initial={{ opacity: 0, x: -4, scale: 0.9 }}
                  animate={{ opacity: 1, x: 0, scale: 1 }}
                  className="absolute left-full ml-2 px-2.5 py-1 rounded-full glass-surface text-xs font-medium text-text-primary whitespace-nowrap pointer-events-none"
                >
                  {item.label}
                </motion.span>
              )}
            </motion.button>
          );
        })}

        {/* 主悬浮球 */}
        <motion.button
          className="absolute flex items-center justify-center w-12 h-12 -ml-6 -mt-6 rounded-full glass-surface press-feedback shadow-[0_4px_20px_rgba(124,58,237,0.25)]"
          onClick={() => setExpanded((v) => !v)}
          whileHover={{ scale: 1.08 }}
          whileTap={{ scale: 0.94 }}
          title={expanded ? "收起导航" : "展开导航"}
          aria-label={expanded ? "收起导航" : "展开导航"}
        >
          <motion.span
            animate={{ rotate: expanded ? 90 : 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="flex items-center justify-center"
          >
            {expanded ? (
              <X size={20} className="text-text-primary" />
            ) : (
              <Sparkles size={20} className="text-purple-500" />
            )}
          </motion.span>
        </motion.button>
      </div>
    </>
  );
}
