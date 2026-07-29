import { useState } from "react";
import { Upload, FileText } from "lucide-react";
import { Button } from "../components/ui/button";
import { Textarea } from "../components/ui/textarea";
import { Badge } from "../components/ui/badge";
import { mockParsedResults } from "../data/mock";

export default function BatchFetchPage() {
  const [links, setLinks] = useState("");
  const [parsed, setParsed] = useState<typeof mockParsedResults | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const handleParse = () => {
    setParsed(mockParsedResults);
    setSelected(new Set());
  };

  const toggleSelect = (index: number) => {
    const next = new Set(selected);
    if (next.has(index)) next.delete(index);
    else next.add(index);
    setSelected(next);
  };

  const toggleAll = () => {
    if (!parsed) return;
    if (selected.size === parsed.length) setSelected(new Set());
    else setSelected(new Set(parsed.map((_, i) => i)));
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-6 h-14 border-b border-border-light">
        <h1 className="text-display font-semibold text-text-primary">批量抓取</h1>
      </div>

      {/* Input Area */}
      <div className="p-6 pb-0">
        <div className="flex gap-2">
          <Textarea
            placeholder="在此粘贴抖音链接，每行一个&#10;支持视频链接、图文链接、用户主页链接"
            value={links}
            onChange={(e) => setLinks(e.target.value)}
            className="flex-1"
          />
          <Button variant="secondary" className="h-auto flex-col gap-1 px-4">
            <Upload size={20} />
            <span className="text-xs">导入文件</span>
          </Button>
        </div>
        <div className="flex justify-end mt-3">
          <Button onClick={handleParse} disabled={!links.trim()}>
            开始解析
          </Button>
        </div>
      </div>

      {/* Divider */}
      <div className="mt-4 border-t border-border-light" />

      {/* Results */}
      {parsed && (
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-6 py-2 border-b border-border-light">
            <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
              <input
                type="checkbox"
                className="w-4 h-4 accent-purple-500"
                checked={selected.size === parsed.length}
                onChange={toggleAll}
              />
              全选
            </label>
            <span className="text-xs text-text-secondary">
              已选 {selected.size} / 共 {parsed.length} 项
            </span>
          </div>
          <div className="flex-1 overflow-y-auto">
            {parsed.map((item, i) => (
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
          {/* Bottom bar */}
          <div className="flex items-center gap-3 px-6 h-14 border-t border-border-light bg-white">
            <span className="text-xs text-text-secondary flex-1">
              下载目录: D:\Downloads\DouyinCatcher
            </span>
            <Button disabled={selected.size === 0}>开始下载 ({selected.size})</Button>
          </div>
        </div>
      )}

      {/* Empty state (no results yet) */}
      {!parsed && (
        <div className="flex-1 flex items-center justify-center text-text-disabled">
          <div className="text-center">
            <FileText size={48} className="mx-auto mb-3 opacity-50" />
            <p className="text-sm">粘贴链接后点击"开始解析"</p>
          </div>
        </div>
      )}
    </div>
  );
}