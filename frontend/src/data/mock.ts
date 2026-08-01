import type { TaskItem, ParsedURL, CookieItem, AppConfig, NavItem } from "../types";

export const mockNavItems: NavItem[] = [
  { id: "download", path: "/download", label: "下载任务", icon: "download" },
  { id: "batch-fetch", path: "/batch-fetch", label: "批量抓取", icon: "link" },
  { id: "profile-fetch", path: "/profile-fetch", label: "主页抓取", icon: "user" },
  { id: "cookie", path: "/cookie", label: "Cookie 配置", icon: "key" },
  { id: "settings", path: "/settings", label: "设置", icon: "settings" },
];

export const mockTasks: TaskItem[] = [
  {
    id: 1, taskId: 1, awemeId: "123456", title: "美丽的海边日落风景欣赏",
    author: "旅行者", type: "video", duration: "15s", imageCount: 0,
    coverUrl: "", status: "downloading", progress: 45,
    downloadedBytes: 4500000, totalBytes: 10000000,
    createdAt: "2026-07-28T10:00:00",
  },
  {
    id: 2, taskId: 1, awemeId: "123457", title: "城市夜景合集",
    author: "摄影师", type: "long_video", duration: "12:30", imageCount: 0,
    coverUrl: "", status: "completed", progress: 100,
    downloadedBytes: 50000000, totalBytes: 50000000,
    createdAt: "2026-07-28T10:01:00",
  },
  {
    id: 3, taskId: 1, awemeId: "123458", title: "美食教程图集",
    author: "美食家", type: "image_set", duration: "", imageCount: 9,
    coverUrl: "", status: "paused", progress: 35,
    downloadedBytes: 8000000, totalBytes: 23000000,
    createdAt: "2026-07-28T10:02:00",
  },
  {
    id: 4, taskId: 1, awemeId: "123459", title: "失败的视频标题",
    author: "作者", type: "video", duration: "1m20s", imageCount: 0,
    coverUrl: "", status: "failed", progress: 12,
    downloadedBytes: 1200000, totalBytes: 10000000,
    failReason: "Cookie 已失效，请更新 Cookie",
    createdAt: "2026-07-28T10:03:00",
  },
  {
    id: 5, taskId: 2, awemeId: "123460", title: "等待下载的视频",
    author: "作者", type: "video", duration: "30s", imageCount: 0,
    coverUrl: "", status: "pending", progress: 0,
    downloadedBytes: 0, totalBytes: 5000000,
    createdAt: "2026-07-28T10:04:00",
  },
];

export const mockParsedResults: ParsedURL[] = [
  { url: "https://v.douyin.com/xxxx1/", type: "video", awemeId: "111", title: "海岛度假Vlog", author: "旅行者", coverUrl: "", duration: "45s" },
  { url: "https://v.douyin.com/xxxx2/", type: "image_set", awemeId: "112", title: "手工蛋糕制作过程", author: "美食家", coverUrl: "", imageCount: 12 },
  { url: "https://v.douyin.com/xxxx3/", type: "long_video", awemeId: "113", title: "纪录片：亚马逊探秘", author: "探索频道", coverUrl: "", duration: "45:00" },
  { url: "https://v.douyin.com/xxxx4/", type: "video", awemeId: "114", title: "猫咪日常", author: "铲屎官", coverUrl: "", duration: "15s" },
  { url: "https://v.douyin.com/xxxx5/", type: "video", awemeId: "115", title: "街头采访：你幸福吗", author: "街访达人", coverUrl: "", duration: "3m20s" },
];

export const mockCookies: CookieItem[] = [
  { id: 1, label: "账号1", status: "valid", lastUsed: "2026-07-28 10:30", lastCheck: "2026-07-28 10:30", failCount: 0 },
  { id: 2, label: "账号2", status: "invalid", lastUsed: "2026-07-27 18:22", lastCheck: "2026-07-27 18:22", failCount: 3 },
  { id: 3, label: "账号3", status: "untested", lastUsed: "", lastCheck: "", failCount: 0 },
];

export const mockConfig: AppConfig = {
  downloadDir: "D:\\Downloads\\DouyinCatcher",
  concurrency: 3,
  chunkSize: 1,
  metadataFormats: ["json"],
  titleTruncate: 20,
};