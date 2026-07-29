import { Play, Pause, FolderOpen, RefreshCw, RotateCw } from "lucide-react";
import { Progress } from "../ui/progress";
import { Badge } from "../ui/badge";
import type { TaskItem as TaskItemType } from "../../types";

const statusConfig = {
  pending: { label: "等待中", progressVariant: "default" as const, icon: null },
  downloading: { label: "下载中", progressVariant: "default" as const, icon: <Pause size={14} /> },
  paused: { label: "已暂停", progressVariant: "paused" as const, icon: <Play size={14} /> },
  completed: { label: "完成", progressVariant: "success" as const, icon: <FolderOpen size={14} /> },
  failed: { label: "失败", progressVariant: "error" as const, icon: <RefreshCw size={14} /> },
};

export function TaskItem({ task }: { task: TaskItemType }) {
  const config = statusConfig[task.status];
  const isFailed = task.status === "failed";
  const typeBadgeVariant = task.type === "video" ? "video" : task.type === "image_set" ? "image_set" : "long_video";

  return (
    <div className={`flex items-center gap-3 px-6 py-3 border-b border-border-light hover:bg-bg-hover transition-colors ${isFailed ? "bg-red-50 border-l-3 border-l-error" : ""}`}>
      {/* Thumbnail */}
      <div className="w-16 h-16 rounded-sm bg-bg-hover flex-shrink-0 flex items-center justify-center text-text-disabled text-xs">
        {task.coverUrl ? (
          <img src={task.coverUrl} alt={task.title} className="w-full h-full object-cover rounded-sm" />
        ) : (
          "封面"
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-text-primary truncate">{task.title}</span>
          <Badge variant={typeBadgeVariant} />
        </div>
        <div className="flex items-center gap-2 mt-0.5 text-xs text-text-secondary">
          <span>@{task.author}</span>
          <span>·</span>
          <span>{task.duration || (task.imageCount ? `${task.imageCount}张图` : "")}</span>
        </div>
        {isFailed && task.failReason && (
          <div className="mt-1 text-xs text-error">⚠ {task.failReason}</div>
        )}
      </div>

      {/* Progress */}
      <div className="w-44 flex-shrink-0">
        <Progress value={task.progress} variant={config.progressVariant} />
        <div className="text-xs text-text-secondary text-center mt-0.5">
          {task.status === "completed" ? "完成" : task.status === "failed" ? "失败" : task.status === "paused" ? "已暂停" : `${task.progress}%`}
        </div>
      </div>

      {/* Action */}
      <div className="flex-shrink-0">
        <button className="w-8 h-8 flex items-center justify-center rounded-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors">
          {config.icon || <RotateCw size={14} />}
        </button>
      </div>
    </div>
  );
}