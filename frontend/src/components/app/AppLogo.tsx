/**
 * 应用品牌 Logo：渐变圆角方形 + "向下三角 + 托盘" 字形
 * 倒三角既是 V（Video），又是下载箭头；托盘代表"抓取落盘"。
 * 与打包图标（assets/app-icon.svg → tauri icon 生成）保持同一设计。
 */
export function AppLogo({ size = 26, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 128 128"
      fill="none"
      className={className}
      aria-label="VideoGetTool"
      role="img"
    >
      <defs>
        <linearGradient id="vgt-logo-g" x1="18" y1="8" x2="110" y2="120" gradientUnits="userSpaceOnUse">
          <stop stopColor="#8B5CF6" />
          <stop offset="0.55" stopColor="#7C3AED" />
          <stop offset="1" stopColor="#C026D3" />
        </linearGradient>
      </defs>
      {/* 渐变圆角底板 */}
      <rect x="4" y="4" width="120" height="120" rx="30" fill="url(#vgt-logo-g)" />
      {/* 向下三角（V / 下载箭头） */}
      <path
        d="M36.5 38h55c5.2 0 8.2 5.9 5.1 10.1L70.1 84.3a7.6 7.6 0 0 1-12.2 0L31.4 48.1C28.3 43.9 31.3 38 36.5 38Z"
        fill="#FFFFFF"
      />
      {/* 托盘 */}
      <rect x="36" y="90" width="56" height="11" rx="5.5" fill="#FFFFFF" fillOpacity="0.9" />
    </svg>
  );
}
