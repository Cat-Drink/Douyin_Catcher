import { useState } from "react";
import { Plus, RefreshCw, Trash2, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "../components/ui/button";
import { StatusDot } from "../components/ui/status-dot";
import { mockCookies } from "../data/mock";
import type { CookieItem } from "../types";

export default function CookiePage() {
  const [cookies] = useState<CookieItem[]>(mockCookies);
  const [tutorialOpen, setTutorialOpen] = useState(false);

  const stats = {
    total: cookies.length,
    valid: cookies.filter((c) => c.status === "valid").length,
    invalid: cookies.filter((c) => c.status === "invalid").length,
    untested: cookies.filter((c) => c.status === "untested").length,
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-6 h-14 border-b border-border-light">
        <h1 className="text-display font-semibold text-text-primary">Cookie 配置</h1>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2 px-6 h-12 border-b border-border-light">
        <Button size="sm">
          <Plus size={14} className="mr-1" /> 添加 Cookie
        </Button>
        <Button variant="secondary" size="sm">
          <RefreshCw size={14} className="mr-1" /> 全部测试
        </Button>
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setTutorialOpen(!tutorialOpen)}
        >
          {tutorialOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          教程
        </Button>
      </div>

      {/* Cookie List */}
      <div className="flex-1 overflow-y-auto">
        {cookies.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-text-disabled">
            <div className="text-4xl mb-3">🍪</div>
            <p className="text-base font-medium text-text-primary">还没有配置 Cookie</p>
            <p className="text-sm mt-1">配置 Cookie 后才能下载视频</p>
            <Button className="mt-4" size="sm">+ 添加 Cookie</Button>
          </div>
        ) : (
          <div>
            <div className="px-6 py-1 text-xs text-text-secondary font-medium border-b border-border-light bg-bg-gray">
              Cookie 列表
            </div>
            {cookies.map((cookie) => (
              <div
                key={cookie.id}
                className="flex items-center gap-4 px-6 h-12 border-b border-border-light hover:bg-bg-hover transition-colors"
              >
                <StatusDot status={cookie.status} />
                <span className="text-sm font-medium text-text-primary w-20">{cookie.label}</span>
                <span className={`text-xs ${
                  cookie.status === "valid" ? "text-success" :
                  cookie.status === "invalid" ? "text-error" : "text-warning"
                }`}>
                  {cookie.status === "valid" ? "有效" : cookie.status === "invalid" ? "失效" : "未测试"}
                </span>
                <span className="text-xs text-text-disabled flex-1">
                  最后使用: {cookie.lastUsed || "-"}
                </span>
                <Button variant="ghost" size="sm" className="text-xs">测试</Button>
                <button className="text-text-disabled hover:text-error transition-colors">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tutorial */}
      {tutorialOpen && (
        <div className="border-t border-border-light">
          <div className="px-6 py-4 bg-bg-gray">
            <h3 className="text-sm font-semibold text-text-primary mb-2">Cookie 获取教程</h3>
            <ol className="text-xs text-text-secondary space-y-2 list-decimal list-inside">
              <li>浏览器打开 douyin.com 并登录你的账号</li>
              <li>按 F12 打开开发者工具，切换到 Network（网络）标签</li>
              <li>刷新页面，点击任意网络请求</li>
              <li>在 Request Headers 中找到 Cookie 字段，右键复制完整值</li>
              <li>回到应用，在 Cookie 配置页粘贴并点击"添加并测试"</li>
            </ol>
          </div>
        </div>
      )}

      {/* Bottom Status */}
      <div className="flex items-center gap-4 px-6 h-8 border-t border-border-light text-xs text-text-secondary">
        <span>共 {stats.total} 个 Cookie</span>
        <span className="text-success">有效 {stats.valid}</span>
        <span className="text-error">失效 {stats.invalid}</span>
        <span className="text-warning">未测试 {stats.untested}</span>
      </div>
    </div>
  );
}