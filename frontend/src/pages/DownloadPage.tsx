import { useState, useEffect, useCallback } from "react";
import { Search, RefreshCw } from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { TaskItem } from "../components/app/TaskItem";
import { useTaskStore } from "../store/taskStore";
import { useWebSocket } from "../hooks/useWebSocket";
import { useToastStore } from "../store/toastStore";
import * as api from "../lib/api";
import { useNavigate } from "react-router-dom";
import type { WsMessage } from "../hooks/useWebSocket";

export default function DownloadPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const {
    items, loading, error,
    loadTasks, applyProgressUpdate,
    pauseItem, resumeItem, retryItem, pauseAll, resumeAll, clearCompleted,
  } = useTaskStore();
  const { addToast } = useToastStore();

  const handleDeleteItem = async (taskId: number) => {
    try {
      await api.deleteTask(taskId);
      addToast("任务已删除", "success");
      loadTasks();
    } catch (e) {
      addToast("删除失败", "error");
    }
  };

  // 加载任务数据
  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  // WebSocket 进度更新
  const onWsMessage = useCallback(
    (msg: WsMessage) => {
      if (msg.type === "progress" && msg.updates) {
        for (const update of msg.updates) {
          applyProgressUpdate(update);
        }
      }
    },
    [applyProgressUpdate],
  );

  const { connected } = useWebSocket(onWsMessage);

  // 过滤
  const filtered = items.filter(
    (t) =>
      t.title.toLowerCase().includes(search.toLowerCase()) ||
      t.author.toLowerCase().includes(search.toLowerCase()),
  );

  // 统计
  const stats = {
    total: items.length,
    downloading: items.filter((t) => t.status === "downloading").length,
    completed: items.filter((t) => t.status === "completed").length,
    failed: items.filter((t) => t.status === "failed").length,
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 h-14 border-b border-border-light">
        <h1 className="text-display font-semibold text-text-primary">下载任务</h1>
        <div className="flex items-center gap-2">
          {!connected && (
            <span className="text-xs text-error flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-error inline-block" />
              服务未连接
            </span>
          )}
          {connected && (
            <span className="text-xs text-success flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-success inline-block" />
              已连接
            </span>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={loadTasks}
            disabled={loading}
            title="刷新"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </Button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2 px-6 h-12 border-b border-border-light">
        <Button variant="ghost" size="sm" onClick={pauseAll}>全部暂停</Button>
        <Button variant="ghost" size="sm" onClick={resumeAll}>全部开始</Button>
        <Button variant="ghost" size="sm" className="text-error" onClick={clearCompleted}>清空已完成</Button>
        <div className="flex-1" />
        <div className="relative w-48">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-disabled" />
          <Input
            placeholder="搜索任务..."
            className="pl-8 h-7 text-xs"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="mx-6 mt-3 p-3 bg-red-50 border border-red-200 rounded-sm">
          <div className="flex items-center gap-2 text-sm text-error">
            <span>⚠</span>
            <span>{error}</span>
            <Button variant="ghost" size="sm" onClick={loadTasks} className="ml-auto">
              重试
            </Button>
          </div>
        </div>
      )}

      {/* Task List */}
      <div className="flex-1 overflow-y-auto">
        {loading && items.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-text-disabled">
            <RefreshCw size={32} className="animate-spin mb-3" />
            <p className="text-sm">正在加载任务列表...</p>
          </div>
        ) : filtered.length === 0 && !error ? (
          <div className="flex flex-col items-center justify-center h-full text-text-disabled">
            <div className="text-4xl mb-3">📥</div>
            <p className="text-base font-medium text-text-primary">
              {search ? "没有匹配的任务" : "还没有下载任务"}
            </p>
            <p className="text-sm mt-1">
              {search ? "试试其他关键词" : "前往链接抓取页添加链接"}
            </p>
            {!search && (
              <Button className="mt-4" size="sm" onClick={() => navigate("/batch-fetch")}>
                去添加链接
              </Button>
            )}
          </div>
        ) : (
          <div>
            {filtered.map((task) => (
              <TaskItem
                key={task.id}
                task={task}
                onPause={pauseItem}
                onResume={resumeItem}
                onRetry={retryItem}
                onDelete={handleDeleteItem}
              />
            ))}
          </div>
        )}
      </div>

      {/* Bottom Status */}
      <div className="flex items-center gap-4 px-6 h-8 border-t border-border-light text-xs text-text-secondary">
        <span>总数 {stats.total}</span>
        {stats.downloading > 0 && <span className="text-purple-500">下载中 {stats.downloading}</span>}
        {stats.completed > 0 && <span className="text-success">已完成 {stats.completed}</span>}
        {stats.failed > 0 && <span className="text-error">失败 {stats.failed}</span>}
      </div>
    </div>
  );
}