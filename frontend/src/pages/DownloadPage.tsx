import { useState } from "react";
import { Search, RotateCw } from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { TaskItem } from "../components/app/TaskItem";
import { mockTasks } from "../data/mock";
import type { TaskItem as TaskItemType } from "../types";

export default function DownloadPage() {
  const [search, setSearch] = useState("");
  const [tasks] = useState<TaskItemType[]>(mockTasks);

  const filtered = tasks.filter(
    (t) =>
      t.title.toLowerCase().includes(search.toLowerCase()) ||
      t.author.toLowerCase().includes(search.toLowerCase()),
  );

  const stats = {
    total: tasks.length,
    downloading: tasks.filter((t) => t.status === "downloading").length,
    completed: tasks.filter((t) => t.status === "completed").length,
    failed: tasks.filter((t) => t.status === "failed").length,
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 h-14 border-b border-border-light">
        <h1 className="text-display font-semibold text-text-primary">下载任务</h1>
        <Button variant="ghost" size="icon">
          <RotateCw size={16} />
        </Button>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2 px-6 h-12 border-b border-border-light">
        <Button variant="ghost" size="sm">全部暂停</Button>
        <Button variant="ghost" size="sm">全部开始</Button>
        <Button variant="ghost" size="sm" className="text-error">清空已完成</Button>
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

      {/* Task List */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-text-disabled">
            <div className="text-4xl mb-3">📥</div>
            <p className="text-base font-medium text-text-primary">还没有下载任务</p>
            <p className="text-sm mt-1">前往链接抓取页添加链接</p>
            <Button className="mt-4" size="sm">去添加链接</Button>
          </div>
        ) : (
          <div>
            {filtered.map((task) => (
              <TaskItem key={task.id} task={task} />
            ))}
          </div>
        )}
      </div>

      {/* Bottom Status */}
      <div className="flex items-center gap-4 px-6 h-8 border-t border-border-light text-xs text-text-secondary">
        <span>总数 {stats.total}</span>
        <span className="text-purple-500">下载中 {stats.downloading}</span>
        <span className="text-success">已完成 {stats.completed}</span>
        <span className="text-error">失败 {stats.failed}</span>
      </div>
    </div>
  );
}