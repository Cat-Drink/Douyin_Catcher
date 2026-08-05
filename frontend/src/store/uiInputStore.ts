/**
 * UI 输入缓存 Store
 *
 * 用于缓存各页面输入框的内容，避免切换页面（组件卸载）后输入丢失。
 * 使用 localStorage 持久化，使输入内容在页面切换甚至应用重启后仍可恢复。
 *
 * 相关 issue：issue-7（输入框内容无法缓存，切换页面后丢失）
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiInputStore {
  /** 批量抓取页：链接输入框内容 */
  batchLinks: string;
  /** 主页抓取页：用户主页链接输入框内容 */
  profileHomeUrl: string;
  /** 下载任务页：搜索框内容 */
  downloadSearch: string;

  setBatchLinks: (value: string) => void;
  setProfileHomeUrl: (value: string) => void;
  setDownloadSearch: (value: string) => void;
}

export const useUiInputStore = create<UiInputStore>()(
  persist(
    (set) => ({
      batchLinks: "",
      profileHomeUrl: "",
      downloadSearch: "",

      setBatchLinks: (value) => set({ batchLinks: value }),
      setProfileHomeUrl: (value) => set({ profileHomeUrl: value }),
      setDownloadSearch: (value) => set({ downloadSearch: value }),
    }),
    {
      name: "ui-input-cache",
    },
  ),
);
