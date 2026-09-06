import type { Transition, Variants } from "framer-motion";

/**
 * 全局动效系统参数 —— 所有微动效统一从这里取值，
 * 保证全应用弹性曲线与时长的一致性（Raycast/Linear 风格）。
 */

/** 弹性贝塞尔（抽屉展开 / 主移动效） */
export const EASE_OUT_EXPO = [0.16, 1, 0.3, 1] as const;

/** 按压回弹 */
export const EASE_SPRING_PRESS = [0.34, 1.56, 0.64, 1] as const;

/** Dock 抽屉展开：轻微过冲的 spring */
export const springDrawer: Transition = {
  type: "spring",
  stiffness: 420,
  damping: 32,
  mass: 0.9,
};

/** 内容高度自适应 / 卡片形变 */
export const springMorph: Transition = {
  type: "spring",
  stiffness: 300,
  damping: 30,
};

/** 页面/Tab 切换：opacity 0->1 + y 12->0，250~350ms */
export const pageTransition: Transition = {
  duration: 0.3,
  ease: EASE_OUT_EXPO,
};

/** 页面切换 variants，配合 AnimatePresence 使用 */
export const pageVariants: Variants = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8, transition: { duration: 0.18, ease: "easeIn" } },
};

/** 抽屉导航项交错出现（收起时高度折叠为 0） */
export const dockItemVariants: Variants = {
  collapsed: { opacity: 0, x: -10, scale: 0.85, height: 0, marginBottom: 0 },
  expanded: (i: number) => ({
    opacity: 1,
    x: 0,
    scale: 1,
    height: 36,
    marginBottom: 4,
    transition: { delay: 0.04 * i, duration: 0.25, ease: EASE_OUT_EXPO },
  }),
};

/** 悬浮上浮 + 阴影扩散 */
export const hoverLift = {
  whileHover: { y: -2, transition: { duration: 0.2, ease: EASE_OUT_EXPO } },
  whileTap: { scale: 0.96 },
} as const;

/** 结果卡片瀑布流渐入 */
export const resultItemVariants: Variants = {
  hidden: { opacity: 0, y: 16, scale: 0.99 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { delay: Math.min(i * 0.04, 0.4), duration: 0.3, ease: EASE_OUT_EXPO },
  }),
};
