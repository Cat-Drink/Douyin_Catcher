import { useState } from "react";
import { FolderOpen, Download } from "lucide-react";
import { Button } from "../components/ui/button";
import { mockConfig } from "../data/mock";

export default function SettingsPage() {
  const [config] = useState(mockConfig);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-6 h-14 border-b border-border-light">
        <h1 className="text-display font-semibold text-text-primary">设置</h1>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Download Settings */}
        <section>
          <h2 className="text-h3 font-semibold text-text-primary mb-3">下载设置</h2>
          <div className="border border-border-light rounded-lg overflow-hidden">
            <div className="px-5 py-4 space-y-0">
              <div className="flex items-center justify-between h-12">
                <span className="text-sm text-text-primary">下载目录</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-secondary max-w-60 truncate">{config.downloadDir}</span>
                  <Button variant="secondary" size="sm">
                    <FolderOpen size={14} className="mr-1" /> 浏览...
                  </Button>
                </div>
              </div>
              <div className="border-t border-border-light" />
              <div className="flex items-center justify-between h-12">
                <span className="text-sm text-text-primary">并发下载数</span>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-text-secondary">1</span>
                  <div className="w-40 h-2 bg-border-light rounded-full relative">
                    <div
                      className="h-full bg-purple-500 rounded-full"
                      style={{ width: `${((config.concurrency - 1) / 9) * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-text-secondary">10</span>
                  <span className="text-sm font-semibold text-purple-500 w-4 text-center">{config.concurrency}</span>
                </div>
              </div>
              <div className="border-t border-border-light" />
              <div className="flex items-center justify-between h-12">
                <span className="text-sm text-text-primary">单文件分块大小</span>
                <span className="text-sm text-text-secondary">{config.chunkSize} MB</span>
              </div>
              <div className="border-t border-border-light" />
              <div className="flex items-center justify-between h-12">
                <span className="text-sm text-text-primary">失败重试次数</span>
                <span className="text-sm text-text-disabled">3 次（固定）</span>
              </div>
            </div>
          </div>
        </section>

        {/* Metadata Settings */}
        <section>
          <h2 className="text-h3 font-semibold text-text-primary mb-3">元数据设置</h2>
          <div className="border border-border-light rounded-lg px-5 py-4">
            <div className="flex items-center gap-6">
              <span className="text-sm text-text-primary">元数据保存格式</span>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" className="w-4 h-4 accent-purple-500" defaultChecked />
                JSON
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" className="w-4 h-4 accent-purple-500" />
                CSV
              </label>
            </div>
          </div>
        </section>

        {/* Logs */}
        <section>
          <h2 className="text-h3 font-semibold text-text-primary mb-3">日志与反馈</h2>
          <div className="border border-border-light rounded-lg px-5 py-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-sm text-text-primary">日志位置</span>
                <p className="text-xs text-text-disabled mt-0.5">%APPDATA%\DouyinCatcher\logs\app.log</p>
              </div>
              <Button variant="secondary" size="sm">
                <Download size={14} className="mr-1" /> 导出日志
              </Button>
            </div>
          </div>
        </section>

        {/* About */}
        <section>
          <h2 className="text-h3 font-semibold text-text-primary mb-3">关于</h2>
          <div className="border border-border-light rounded-lg px-5 py-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-text-primary">撷风拾影 (XieFengShiYing)</p>
                <p className="text-xs text-text-secondary mt-0.5">版本: v0.2.3</p>
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" disabled>检查更新</Button>
                <Button variant="secondary" size="sm">开源仓库</Button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}