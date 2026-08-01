import * as React from "react";
import { cn } from "../../lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "video" | "image_set" | "long_video" | "default";
}

const variantStyles = {
  video: "bg-purple-100 text-purple-600",
  image_set: "bg-blue-100 text-blue-700",
  long_video: "bg-orange-100 text-orange-700",
  default: "bg-bg-gray text-text-secondary",
};

const typeLabels = {
  video: "视频",
  image_set: "图文",
  long_video: "长视频",
  default: "未知",
};

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-sm px-2 py-0.5 text-xs font-medium",
        variantStyles[variant],
        className,
      )}
      {...props}
    >
      {typeLabels[variant]}
    </div>
  );
}

export { Badge, typeLabels as badgeTypeLabels };