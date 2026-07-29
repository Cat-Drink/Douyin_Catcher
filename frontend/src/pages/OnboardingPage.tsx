import { useState } from "react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";

type Step = "welcome" | "directory" | "cookie" | "complete";

export default function OnboardingPage() {
  const [step, setStep] = useState<Step>("welcome");
  const [downloadDir, setDownloadDir] = useState("D:\\Downloads\\DouyinCatcher");
  const [cookieValue, setCookieValue] = useState("");
  const [cookieLabel, setCookieLabel] = useState("账号1");

  const stepIndex = ["welcome", "directory", "cookie", "complete"].indexOf(step);

  return (
    <div className="flex flex-col items-center justify-center h-screen bg-bg-base">
      {/* Step Indicator */}
      <div className="flex items-center gap-2 mb-8">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className={`w-2 h-2 rounded-full transition-colors ${
              i <= stepIndex ? "bg-purple-500" : "bg-border-light"
            }`}
          />
        ))}
      </div>

      {/* Welcome */}
      {step === "welcome" && (
        <div className="text-center">
          <div className="w-24 h-24 rounded-2xl bg-purple-500 flex items-center justify-center text-white text-3xl font-bold mx-auto mb-6">
            撷
          </div>
          <h1 className="text-display font-semibold text-text-primary mb-2">欢迎使用撷风拾影</h1>
          <p className="text-sm text-text-secondary mb-2">一款让你轻松下载抖音视频的桌面工具</p>
          <p className="text-xs text-text-disabled mb-8">无需命令行，配置 Cookie 后即可一键下载</p>
          <Button onClick={() => setStep("directory")}>开始使用</Button>
        </div>
      )}

      {/* Directory */}
      {step === "directory" && (
        <div className="w-96">
          <h2 className="text-h2 font-semibold text-text-primary mb-2">步骤 1：设置下载目录</h2>
          <p className="text-sm text-text-secondary mb-6">选择视频文件保存的位置，建议使用默认目录。</p>
          <div className="flex gap-2">
            <Input value={downloadDir} onChange={(e) => setDownloadDir(e.target.value)} />
            <Button variant="secondary">浏览...</Button>
          </div>
          <p className="text-xs text-info mt-2">默认目录为系统下载文件夹下的 DouyinCatcher 子文件夹，可随时在设置中修改。</p>
          <div className="flex justify-between mt-8">
            <Button variant="ghost" disabled>上一步</Button>
            <Button onClick={() => setStep("cookie")}>下一步</Button>
          </div>
        </div>
      )}

      {/* Cookie */}
      {step === "cookie" && (
        <div className="w-96">
          <h2 className="text-h2 font-semibold text-text-primary mb-2">步骤 2：配置 Cookie</h2>
          <p className="text-sm text-text-secondary mb-6">抖音需要登录态才能访问视频数据，请按教程获取 Cookie。</p>

          <div className="bg-bg-gray rounded-sm p-4 mb-4 text-xs text-text-secondary space-y-1">
            <p className="font-medium text-text-primary mb-1">Cookie 获取教程（简版）</p>
            <p>1. 浏览器打开 douyin.com 并登录</p>
            <p>2. 按 F12 打开开发者工具 → Network 标签</p>
            <p>3. 刷新页面，点任意请求，复制 Request Headers 里的 Cookie 值</p>
            <p className="text-purple-500 mt-1">完整教程见 Cookie 配置页 →</p>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Cookie 内容</label>
              <Textarea
                placeholder="在此粘贴 Cookie 字符串..."
                value={cookieValue}
                onChange={(e) => setCookieValue(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">标签</label>
              <Input value={cookieLabel} onChange={(e) => setCookieLabel(e.target.value)} />
            </div>
          </div>

          <div className="flex justify-between mt-8">
            <Button variant="ghost" onClick={() => setStep("directory")}>上一步</Button>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setStep("complete")}>跳过，稍后配置</Button>
              <Button onClick={() => setStep("complete")} disabled={!cookieValue.trim()}>测试 Cookie</Button>
            </div>
          </div>
        </div>
      )}

      {/* Complete */}
      {step === "complete" && (
        <div className="text-center">
          <div className="w-16 h-16 rounded-full bg-success flex items-center justify-center text-white text-3xl mx-auto mb-6">
            ✓
          </div>
          <h1 className="text-display font-semibold text-text-primary mb-2">配置完成！</h1>
          <p className="text-sm text-text-secondary mb-8">现在可以开始下载抖音视频了</p>
          <Button onClick={() => window.location.href = "/download"}>进入应用</Button>
        </div>
      )}
    </div>
  );
}