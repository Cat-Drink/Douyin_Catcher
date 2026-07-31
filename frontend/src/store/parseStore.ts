/** 解析与抓取状态管理 - Zustand Store */

import { create } from "zustand";
import * as api from "../lib/api";

/** 前端展示用的解析结果项 */
export interface ParsedResult {
  index: number;
  url: string;
  title: string;
  author: string;
  type: "video" | "image_set" | "long_video" | "user_home";
  awemeId?: string;
  coverUrl?: string;
  duration?: string;
  imageCount?: number;
  noWatermarkUrl?: string;
  imageUrls?: string[];
  error?: string;
}

interface ParseStore {
  // 批量解析
  batchResults: ParsedResult[];
  batchLoading: boolean;
  batchError: string | null;

  // 主页抓取
  profileResults: ParsedResult[];
  profileLoading: boolean;
  profileError: string | null;

  /** 批量解析链接 */
  parseUrls: (urls: string[]) => Promise<void>;
  /** 清空批量解析结果 */
  clearBatch: () => void;
  /** 移除已入队下载的批量解析项 */
  removeBatchItems: (indices: Set<number>) => void;

  /** 主页抓取 */
  fetchHome: (url: string, maxItems?: number) => Promise<void>;
  /** 清空主页抓取结果 */
  clearProfile: () => void;
  /** 移除已入队下载的主页解析项 */
  removeProfileItems: (indices: Set<number>) => void;

  /** 将勾选结果入队下载，返回实际入队的解析项 */
  downloadSelected: (items: ParsedResult[], downloadDir?: string) => Promise<ParsedResult[]>;
}

export const useParseStore = create<ParseStore>((set) => ({
  batchResults: [],
  batchLoading: false,
  batchError: null,

  profileResults: [],
  profileLoading: false,
  profileError: null,

  parseUrls: async (urls: string[]) => {
    set({ batchLoading: true, batchError: null, batchResults: [] });
    try {
      const rawResults = await api.parseUrls(urls);
      const results: ParsedResult[] = rawResults.map((r: any, i: number) => ({
        index: i,
        url: urls[i] || r.url || "",
        title: r.title || "",
        author: r.author || "",
        type: (r.type as ParsedResult["type"]) || "video",
        awemeId: r.aweme_id,
        coverUrl: r.cover_url,
        duration: r.duration,
        imageCount: r.image_count,
        noWatermarkUrl: r.no_watermark_url || undefined,
        imageUrls: r.image_urls || undefined,
        error: r.error || undefined,
      }));
      set({ batchResults: results, batchLoading: false });
    } catch (e) {
      set({
        batchError: e instanceof Error ? e.message : "解析失败",
        batchLoading: false,
      });
    }
  },

  clearBatch: () => {
    set({ batchResults: [], batchError: null });
  },

  removeBatchItems: (indices) => {
    set((state) => ({
      batchResults: state.batchResults.filter((r) => !indices.has(r.index)),
    }));
  },

  fetchHome: async (url: string, maxItems = 50) => {
    set({ profileLoading: true, profileError: null, profileResults: [] });
    try {
      const result = await api.fetchHome(url, maxItems);
      const results: ParsedResult[] = (result.items || []).map((r: any, i: number) => ({
        index: i,
        url: r.url || "",
        title: r.title || "",
        author: r.author || "",
        type: (r.type as ParsedResult["type"]) || "video",
        awemeId: r.aweme_id,
        coverUrl: r.cover_url,
        duration: r.duration,
        imageCount: r.image_count,
        noWatermarkUrl: r.no_watermark_url || undefined,
        imageUrls: r.image_urls || undefined,
      }));
      set({ profileResults: results, profileLoading: false });
    } catch (e) {
      set({
        profileError: e instanceof Error ? e.message : "抓取失败",
        profileLoading: false,
      });
    }
  },

  clearProfile: () => {
    set({ profileResults: [], profileError: null });
  },

  removeProfileItems: (indices) => {
    set((state) => ({
      profileResults: state.profileResults.filter((r) => !indices.has(r.index)),
    }));
  },

  downloadSelected: async (items: ParsedResult[], downloadDir?: string) => {
    // 仅入队可下载项（跳过 user_home 与解析失败项），返回实际入队的解析项
    const enqueued = items.filter((item) => item.type !== "user_home" && !item.error);
    const downloadItems = enqueued
      .map((item) => ({
        url: item.url,
        title: item.title,
        author: item.author,
        type: item.type === "long_video" ? "long_video" : item.type === "image_set" ? "image_set" : "video",
        aweme_id: item.awemeId,
        cover_url: item.coverUrl,
        image_count: item.imageCount,
        no_watermark_url: item.noWatermarkUrl,
        image_urls: item.imageUrls,
      }));

    if (downloadItems.length === 0) return [];

    await api.startDownload({
      source_type: "batch",
      items: downloadItems,
      download_dir: downloadDir,
    });
    return enqueued;
  },
}));

/** 从文本中提取抖音链接 */
export function extractLinks(text: string): string[] {
  const urlPattern = /https?:\/\/[^\s，。、！？,;；)）\]]+/g;
  const matches = text.match(urlPattern);
  if (!matches) return [];
  return matches.filter((url) => {
    const lower = url.toLowerCase();
    return lower.includes("douyin.com") || lower.includes("iesdouyin.com");
  });
}