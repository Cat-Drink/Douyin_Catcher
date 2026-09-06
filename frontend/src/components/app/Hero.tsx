import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";
import { springMorph, hoverLift } from "../../lib/motion";

/**
 * 居中 Hero 布局容器：
 * - 无结果时输入卡片位于页面正中心（垂直 + 水平黄金位）
 * - 出现结果后卡片自动上移（TranslateY 上弹），下方瀑布流展开结果
 * - 高度/位置变化通过 spring 平滑形变，不整页跳变
 */
export function HeroSection({
  hasResults,
  loading = false,
  hero,
  children,
  footer,
}: {
  /** 是否已有解析结果（决定 Hero 是否上移） */
  hasResults: boolean;
  /** 解析中：卡片边缘出现流动极光呼吸边框 */
  loading?: boolean;
  /** 居中的输入卡片 */
  hero: React.ReactNode;
  /** 结果区（Hero 下方） */
  children?: React.ReactNode;
  /** 固定底部操作条（结果存在时） */
  footer?: React.ReactNode;
}) {
  return (
    <div className="flex-1 flex flex-col overflow-y-auto">
      <motion.div
        layout
        transition={springMorph}
        className={cn(
          "flex flex-col",
          hasResults ? "pt-8 pb-4" : "flex-1 justify-center min-h-[60vh]",
        )}
      >
        <div className="w-full max-w-[42rem] mx-auto px-6">
          <div className={cn(loading && "aurora-border rounded-2xl")}>
            <div
              className="hero-card glass-surface glow-focus rounded-2xl overflow-hidden"
            >
              {hero}
            </div>
          </div>
        </div>
      </motion.div>

      {children}

      {footer}
    </div>
  );
}

/**
 * Hero 卡片底部操作组容器（右下角：导入文件 / 平台 Tag / 解析按钮）
 */
export function HeroActions({ children }: { children: React.ReactNode }) {
  return <div className="flex items-center gap-2 px-4 pb-4 pt-1">{children}</div>;
}

/** 轻量辅助指引 Chip，点击一键填入示例 */
export function HeroChip({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick?: () => void;
}) {
  return (
    <motion.button
      {...hoverLift}
      onClick={onClick}
      className="press-feedback px-3 py-1 rounded-full text-xs text-text-secondary glass-surface hover:text-purple-500 transition-colors"
    >
      {children}
    </motion.button>
  );
}

/** 解析主按钮：输入非空时从禁用灰度弹入炫彩渐变；Loading 时文字淡出 + Spinner */
export function ParseButton({
  disabled,
  loading,
  onClick,
  label = "开始解析",
}: {
  disabled?: boolean;
  loading?: boolean;
  onClick?: () => void;
  label?: string;
}) {
  return (
    <motion.button
      {...hoverLift}
      disabled={disabled || loading}
      onClick={onClick}
      className={cn(
        "relative h-9 px-5 rounded-lg text-sm font-medium text-white overflow-hidden select-none",
        disabled || loading
          ? "bg-border-default text-text-disabled cursor-not-allowed"
          : "bg-gradient-to-r from-purple-600 via-purple-500 to-fuchsia-500 shadow-[0_4px_16px_rgba(124,58,237,0.35)]",
      )}
    >
      <motion.span
        className="flex items-center justify-center gap-1.5"
        animate={{ opacity: loading ? 0 : 1, y: loading ? -6 : 0 }}
        transition={{ duration: 0.18 }}
      >
        {label}
      </motion.span>
      {loading && (
        <motion.span
          className="absolute inset-0 flex items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          <Loader2 size={16} className="animate-spin" />
        </motion.span>
      )}
    </motion.button>
  );
}
