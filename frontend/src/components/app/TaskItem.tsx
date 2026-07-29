import { Play, Pause, RotateCw, FolderOpen, RefreshCw, Trash2 } from "lucide-react";
import { Progress } from "../ui/progress";
import { Badge } from "../ui/badge";
import type { DisplayTask } from "../../store/taskStore";

interface TaskItemProps {
  task: DisplayTask;
  onPause?: (id: number) => void;
  onResume?: (id: number) => void;
  onRetry?: (id: number) => void;
  onDelete?: (id: number) => void;
}

const statusConfig = {
  pending: { label: "等待中", progressVariant: "default" as const, actionIcon: null },
  downloading: { label: "下载中", progressVariant: "default" as const, actionIcon: <Pause size={14} /> },
  paused: { label: "已暂停", progressVariant: "paused" as const, actionIcon: <Play size={14} /> },
  completed: { label: "完成", progressVariant: "success" as const, actionIcon: <FolderOpen size={14} /> },
  failed: { label: "失败", progressVariant: "error" as const, actionIcon: <RefreshCw size={14} /> },
};

export function TaskItem({ task, onPause, onResume, onRetry, onDelete }: TaskItemProps) {
  const config = statusConfig[task.status];
  const isFailed = task.status === "failed";
  const isCompleted = task.status === "completed";
  const typeBadgeVariant = task.type === "video" ? "video" : task.type === "image_set" ? "image_set" : "long_video" as const;

  const handleAction = () => {
    if (task.status === "downloading" && onPause) onPause(task.id);
    else if (task.status === "paused" && onResume) onResume(task.id);
    else if (task.status === "failed" && onRetry) onRetry(task.id);
  };

  return (
    <div className={`flex items-center gap-3 px-6 py-3 border-b border-border-light hover:bg-bg-hover transition-colors ${isFailed ? "bg-red-50 border-l-3 border-l-error" : ""}`}>
      {/* Thumbnail */}
      <div className="w-16 h-16 rounded-sm bg-bg-hover flex-shrink-0 flex items-center justify-center text-text-disabled text-xs">
        {task.coverUrl ? (
          <img src={task.coverUrl} alt={task.title} className="w-full h-full object-cover rounded-sm" />
        ) : (
          <div className="flex flex-col items-center">
            <span className="text-lg">📄</span>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-text-primary truncate">{task.title || task.awemeId || `任务 #${task.id}`}</span>
          <Badge variant={typeBadgeVariant} />
        </div>
        <div className="flex items-center gap-2 mt-0.5 text-xs text-text-secondary">
          <span>@{task.author || "未知作者"}</span>
          <span>·</span>
          <span>{task.duration || (task.imageCount ? `${task.imageCount}张图` : task.type === "image_set" ? "图集" : "")}</span>
        </div>
        {isFailed && task.failReason && (
          <div className="mt-1 text-xs text-error">⚠ {task.failReason}</div>
        )}
      </div>

      {/* Progress */}
      <div className="w-44 flex-shrink-0">
        <Progress value={task.progress} variant={config.progressVariant} />
        <div className="text-xs text-text-secondary text-center mt-0.5">
          {task.status === "completed" ? "完成" : task.status === "failed" ? "失败" : task.status === "paused" ? "已暂停" : `${Math.round(task.progress)}%`}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 flex-shrink-0">
        {task.status !== "completed" && (
          <button
            onClick={handleAction}
            className="w-8 h-8 flex items-center justify-center rounded-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
            title={task.status === "downloading" ? "暂停" : task.status === "paused" ? "恢复" : task.status === "failed" ? "重试" : ""}
          >
            {config.actionIcon || <RotateCw size={14} />}
          </button>
        )}
        {isCompleted && onDelete && (
          <button
            onClick={() => onDelete(task.id)}
            className="w-8 h-8 flex items-center justify-center rounded-sm text-text-secondary hover:bg-bg-hover hover:text-error transition-colors"
            title="删除"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
    </div>
  );
}