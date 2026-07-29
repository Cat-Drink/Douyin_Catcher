import { useState } from "react";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { mockParsedResults } from "../data/mock";

export default function ProfileFetchPage() {
  const [homeUrl, setHomeUrl] = useState("");
  const [fetched, setFetched] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [typeFilter, setTypeFilter] = useState("全部");

  const results = typeFilter === "全部"
    ? mockParsedResults
    : mockParsedResults.filter((r) => {
        if (typeFilter === "视频") return r.type === "video" || r.type === "long_video";
        if (typeFilter === "图文") return r.type === "image_set";
        return true;
      });

  const handleFetch = () => {
    setFetched(true);
    setSelected(new Set());
  };

  const toggleSelect = (index: number) => {
    const next = new Set(selected);
    if (next.has(index)) next.delete(index);
    else next.add(index);
    setSelected(next);
  };

  const toggleAll = () => {
    if (selected.size === results.length) setSelected(new Set());
    else setSelected(new Set(results.map((_, i) => i)));
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-6 h-14 border-b border-border-light">
        <h1 className="text-display font-semibold text-text-primary">主页抓取</h1>
      </div>

      {/* Input */}
      <div className="p-6 pb-3">
        <div className="flex gap-2">
          <Input
            placeholder="粘贴用户主页链接，例如 https://www.douyin.com/user/xxxxx"
            value={homeUrl}
            onChange={(e) => setHomeUrl(e.target.value)}
          />
          <Button onClick={handleFetch} disabled={!homeUrl.trim()}>
            开始抓取
          </Button>
        </div>
      </div>

      {/* Filter bar */}
      {fetched && (
        <div className="px-6 pb-3">
          <div className="flex items-center gap-3 px-4 py-2 bg-bg-gray rounded-sm text-sm">
            <span className="text-text-secondary text-xs">类型:</span>
            {["全部", "视频", "图文", "长视频"].map((f) => (
              <button
                key={f}
                className={`px-2 py-0.5 rounded text-xs transition-colors ${
                  typeFilter === f
                    ? "bg-purple-100 text-purple-600 font-medium"
                    : "text-text-secondary hover:text-text-primary"
                }`}
                onClick={() => setTypeFilter(f)}
              >
                {f}
              </button>
            ))}
            <span className="text-text-secondary text-xs ml-4">数量上限:</span>
            <span className="text-sm font-medium text-text-primary">50</span>
          </div>
        </div>
      )}

      <div className="border-t border-border-light" />

      {/* Results */}
      {fetched && (
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-6 py-2 border-b border-border-light">
            <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
              <input
                type="checkbox"
                className="w-4 h-4 accent-purple-500"
                checked={selected.size === results.length}
                onChange={toggleAll}
              />
              全选
            </label>
            <span className="text-xs text-text-secondary">
              已选 {selected.size} / 共 {results.length} 项
            </span>
          </div>
          <div className="flex-1 overflow-y-auto">
            {results.map((item, i) => (
              <div
                key={i}
                className={`flex items-center gap-3 px-6 py-2 border-b border-border-light hover:bg-bg-hover transition-colors cursor-pointer ${selected.has(i) ? "bg-bg-selected" : ""}`}
                onClick={() => toggleSelect(i)}
              >
                <input
                  type="checkbox"
                  className="w-4 h-4 accent-purple-500 flex-shrink-0"
                  checked={selected.has(i)}
                  onChange={() => toggleSelect(i)}
                />
                <div className="w-12 h-12 rounded-sm bg-bg-hover flex-shrink-0 flex items-center justify-center text-text-disabled text-xs">
                  封面
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-text-primary truncate">{item.title}</div>
                  <div className="text-xs text-text-secondary mt-0.5">@{item.author}</div>
                </div>
                <Badge variant={item.type === "video" ? "video" : item.type === "image_set" ? "image_set" : "long_video"} />
                <span className="text-xs text-text-secondary w-12 text-right flex-shrink-0">
                  {item.duration || (item.imageCount ? `${item.imageCount}张` : "")}
                </span>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-3 px-6 h-14 border-t border-border-light bg-white">
            <span className="text-xs text-text-secondary flex-1">
              下载目录: D:\Downloads\DouyinCatcher
            </span>
            <Button disabled={selected.size === 0}>开始下载 ({selected.size})</Button>
          </div>
        </div>
      )}

      {!fetched && (
        <div className="flex-1 flex items-center justify-center text-text-disabled">
          <div className="text-center">
            <div className="text-4xl mb-3 opacity-50">👤</div>
            <p className="text-sm">输入用户主页链接并点击"开始抓取"</p>
          </div>
        </div>
      )}
    </div>
  );
}