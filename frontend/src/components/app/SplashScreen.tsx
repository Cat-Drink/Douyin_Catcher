import { useCallback, useEffect, useState } from "react";
import { motion, useReducedMotion, type Transition } from "framer-motion";
import { EASE_OUT_EXPO } from "../../lib/motion";
import { useThemeStore } from "../../store/themeStore";
import { WORD_LAYOUT, WORD_VIEWBOX, WORD_WIDTH } from "./splashLettering";

/**
 * 启动页动效（Splash Screen）—— "VideoGetTool" 艺术字描边绘制。
 *
 * 分镜：
 *   1. 主题自适应底色淡入，品牌光斑缓慢漂移；
 *   2. 手工单线字形沿品牌紫渐变从左到右逐笔"落墨"（stroke-draw），
 *      "i" 的墨点下落归位，收笔时整词泛起辉光；
 *   3. 品牌托盘在字底延展，下载箭头（Logo 的 V 隐喻）弹跳落盘；
 *   4. 标语「让视频获取更简单」浮起，随后整页模糊淡出交还应用。
 *
 * 任意点击 / 按键可跳过；系统开启"减弱动态效果"时退化为快速淡入淡出。
 */

const INK_GRADIENT_ID = "splash-ink";

/** 动效分镜时间轴（秒） */
interface Timeline {
  base: number; // 首字母起笔
  stagger: number; // 字母间节奏
  draw: number; // 单条笔画时长
  inner: number; // 同一字母多条笔画的错峰
  tray: number; // 托盘延展
  arrow: number; // 箭头落盘
  tagline: number; // 标语浮起
  exit: number; // 整页退场
  exitDur: number;
}

const PLAY_TL: Timeline = {
  base: 0.35,
  stagger: 0.085,
  draw: 0.7,
  inner: 0.14,
  tray: 2.15,
  arrow: 2.45,
  tagline: 2.62,
  exit: 3.5,
  exitDur: 0.55,
};

const REDUCED_TL: Timeline = {
  base: 0.12,
  stagger: 0.025,
  draw: 0.3,
  inner: 0.06,
  tray: 0.85,
  arrow: 1.0,
  tagline: 1.12,
  exit: 1.9,
  exitDur: 0.3,
};

const ARROW_SPRING: Transition = {
  type: "spring",
  stiffness: 330,
  damping: 16,
};

export function SplashScreen() {
  const reduced = useReducedMotion() ?? false;
  const tl = reduced ? REDUCED_TL : PLAY_TL;
  const { theme } = useThemeStore();
  const [phase, setPhase] = useState<"play" | "exit">("play");
  const [gone, setGone] = useState(false);

  const finish = useCallback(() => setPhase("exit"), []);

  // 到点自动退场；播放期间任意按键可跳过
  useEffect(() => {
    if (phase !== "play") return;
    const timer = window.setTimeout(finish, tl.exit * 1000);
    const onKey = () => finish();
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKey);
    };
  }, [phase, tl.exit, finish]);

  if (gone) return null;

  // 托盘 / 箭头几何：以整词墨迹为中心，托盘略窄于字宽
  const cx = WORD_WIDTH / 2;
  const trayHalf = WORD_WIDTH / 2 - 56;
  const trayY = 126;

  // 字母全部落笔后的辉光增强时机
  const bloomAt =
    tl.base + (WORD_LAYOUT.length - 1) * tl.stagger + tl.draw + tl.inner - 0.25;

  return (
    <motion.div
      className={`fixed inset-0 z-[9999] flex cursor-pointer select-none flex-col items-center justify-center overflow-hidden ${
        theme === "dark" ? "splash-bg-dark" : "splash-bg-light"
      }`}
      initial={{ opacity: 0 }}
      animate={phase === "play" ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 1.045 }}
      transition={
        phase === "play"
          ? { duration: 0.4, ease: EASE_OUT_EXPO }
          : { duration: tl.exitDur, ease: EASE_OUT_EXPO }
      }
      onAnimationComplete={() => {
        if (phase === "exit") setGone(true);
      }}
      onClick={finish}
    >
      {/* 品牌光斑（纯装饰，缓慢漂移） */}
      <div className="splash-blob splash-blob-a" aria-hidden />
      <div className="splash-blob splash-blob-b" aria-hidden />

      <motion.div
        className="relative flex flex-col items-center"
        initial={{ y: 0, scale: 1, opacity: 1 }}
        animate={
          phase === "play"
            ? { y: 0, scale: 1, opacity: 1 }
            : { y: -16, scale: 0.97, opacity: 0 }
        }
        transition={{ duration: Math.min(tl.exitDur, 0.45), ease: EASE_OUT_EXPO }}
      >
        <motion.div
          animate={{
            filter: [
              "drop-shadow(0 0 6px rgba(124, 58, 237, 0.12))",
              "drop-shadow(0 0 22px rgba(124, 58, 237, 0.40))",
            ],
          }}
          transition={{ delay: bloomAt, duration: 0.9, ease: EASE_OUT_EXPO }}
        >
          <svg
            viewBox={WORD_VIEWBOX}
            className="h-auto w-[min(74vw,880px)]"
            role="img"
            aria-label="VideoGetTool"
          >
            <defs>
              <linearGradient
                id={INK_GRADIENT_ID}
                x1="0"
                y1="0"
                x2={WORD_WIDTH}
                y2="80"
                gradientUnits="userSpaceOnUse"
              >
                <stop stopColor="#8B5CF6" />
                <stop offset="0.55" stopColor="#7C3AED" />
                <stop offset="1" stopColor="#C026D3" />
              </linearGradient>
            </defs>

            {/* 艺术字逐笔绘制 */}
            {WORD_LAYOUT.map(({ letter, x, glyph }, i) => {
              const delay = tl.base + i * tl.stagger;
              const strokeAfter = delay + (glyph.paths?.length ?? 0) * tl.inner;
              return (
                <g key={`${letter}-${i}`} transform={`translate(${x} 0)`}>
                  {glyph.paths?.map((d, pi) => (
                    <motion.path
                      key={pi}
                      d={d}
                      fill="none"
                      stroke={`url(#${INK_GRADIENT_ID})`}
                      strokeWidth={9}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      initial={{ pathLength: 0, opacity: 0 }}
                      animate={{ pathLength: 1, opacity: 1 }}
                      transition={{
                        delay: delay + pi * tl.inner,
                        duration: tl.draw,
                        ease: EASE_OUT_EXPO,
                        // pathLength=0 时圆头端帽会显示为零长墨点，用透明度门控到起笔瞬间
                        opacity: { delay: delay + pi * tl.inner, duration: 0.12 },
                      }}
                    />
                  ))}
                  {glyph.circles?.map((c, ci) => (
                    <motion.circle
                      key={`c${ci}`}
                      cx={c.cx}
                      cy={c.cy}
                      r={c.r}
                      fill="none"
                      stroke={`url(#${INK_GRADIENT_ID})`}
                      strokeWidth={9}
                      initial={{ pathLength: 0, opacity: 0 }}
                      animate={{ pathLength: 1, opacity: 1 }}
                      transition={{
                        delay: strokeAfter + ci * tl.inner,
                        duration: tl.draw,
                        ease: EASE_OUT_EXPO,
                        opacity: { delay: strokeAfter + ci * tl.inner, duration: 0.12 },
                      }}
                    />
                  ))}
                  {glyph.dots?.map((dt, di) => (
                    <motion.circle
                      key={`d${di}`}
                      cx={dt.cx}
                      cy={dt.cy}
                      r={dt.r}
                      fill={`url(#${INK_GRADIENT_ID})`}
                      initial={{ y: -12, opacity: 0 }}
                      animate={{ y: 0, opacity: 1 }}
                      transition={{
                        delay: delay + 0.12,
                        duration: 0.35,
                        ease: EASE_OUT_EXPO,
                      }}
                    />
                  ))}
                </g>
              );
            })}

            {/* 托盘延展（"抓取落盘"的容器） */}
            <motion.path
              d={`M ${cx - trayHalf} ${trayY} L ${cx + trayHalf} ${trayY}`}
              fill="none"
              stroke={`url(#${INK_GRADIENT_ID})`}
              strokeWidth={10}
              strokeLinecap="round"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 0.9 }}
              transition={{
                delay: tl.tray,
                duration: 0.45,
                ease: EASE_OUT_EXPO,
                opacity: { delay: tl.tray, duration: 0.1 },
              }}
            />

            {/* 下载箭头（V 隐喻）弹跳落盘 */}
            <motion.path
              d={`M ${cx - 13} 108 L ${cx + 13} 108 L ${cx} ${trayY + 2} Z`}
              fill={`url(#${INK_GRADIENT_ID})`}
              strokeLinejoin="round"
              initial={{ y: -44, opacity: 0, scale: 0.75 }}
              animate={{ y: 0, opacity: 1, scale: 1 }}
              transition={{
                delay: tl.arrow,
                ...(reduced
                  ? { duration: 0.3, ease: EASE_OUT_EXPO }
                  : ARROW_SPRING),
              }}
            />
          </svg>
        </motion.div>

        {/* 标语 */}
        <motion.p
          className="mt-5 pl-[0.42em] text-[13px] font-medium tracking-[0.42em] text-text-secondary dark:text-purple-300/80"
          initial={{ opacity: 0, y: 10 }}
          animate={phase === "play" ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
          transition={{ delay: phase === "play" ? tl.tagline : 0, duration: 0.4, ease: EASE_OUT_EXPO }}
        >
          让视频获取更简单
        </motion.p>
      </motion.div>
    </motion.div>
  );
}
