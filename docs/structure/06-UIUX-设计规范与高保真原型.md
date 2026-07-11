# 抖音抓取器（Douyin_Catcher）UI/UX 设计规范与高保真原型

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 文档名称 | 抖音抓取器 UI/UX 设计规范与高保真原型 |
| 文档版本 | V1.0 |
| 创建日期 | 2026-07-11 |
| 最近更新 | 2026-07-11 |
| 作者 | 设计组 |
| 审批状态 | 待审批 |
| 关联设计文档 | `docs/superpowers/specs/2026-07-11-douyin-catcher-design.md` |
| 适用范围 | Windows 桌面端 PySide6 应用 |
| 技术约束 | QSS 样式表 + Qt 原生组件 |

| 版本 | 日期 | 修改人 | 修改说明 |
|---|---|---|---|
| V1.0 | 2026-07-11 | 设计组 | 首版发布，定义设计系统、组件规范、页面原型、交互规范 |

---

## 2. 设计理念

### 2.1 目标用户画像回顾（非技术用户）

本应用面向**非技术用户**公开发布，用户群体包括但不限于：

- **内容创作者 / 二次创作者**：需要批量下载素材
- **教师 / 研究员**：需要归档教学/研究素材
- **普通用户**：单纯想保存喜欢的抖音视频

**用户特征**：
- 不懂命令行、不懂 API、不懂 HTTP
- 期望"双击安装、点按钮即用"
- 对 Cookie、签名算法等技术概念天然排斥
- 遇到错误容易焦虑，需要明确的下一步指引

**设计含义**：
- Cookie 配置必须有图文教程逐步引导
- 所有错误信息必须翻译成"人话"+下一步建议
- 不让用户看到任何原始异常栈
- 操作反馈即时清晰，避免"点了没反应"的困惑

### 2.2 设计原则

#### 原则 1：简洁（Simplicity）
- 每个页面只做一件事，职责单一
- 默认值合理，让 80% 用户无需改设置
- 信息密度适中，重要操作显眼，次要操作收纳
- 避免装饰性元素，扁平化设计

#### 原则 2：引导式（Guided）
- 首次启动有引导流程，不让用户面对空白界面
- Cookie 教程折叠式呈现，需要时展开
- 危险操作有二次确认
- 表单字段有明确提示文案

#### 原则 3：容错（Fault Tolerance）
- 所有错误都有人话解释 + 下一步建议
- 任务级错误不打断其他任务
- 失败可重试，断点可续传
- 危险操作（清空、删除）有二次确认

#### 原则 4：一致性（Consistency）
- 同类操作在不同页面行为一致
- 色彩语义全局统一（紫=品牌/进行中、绿=成功、红=失败、黄=警告）
- 组件样式全局统一（同一按钮在所有页面外观一致）
- 快捷键与 Windows 习惯一致（Ctrl+A 全选、Delete 删除）

### 2.3 设计约束

| 约束 | 说明 |
|---|---|
| UI 框架 | PySide6 (Qt 6.6+)，单进程，Qt 主线程跑 UI |
| 样式方案 | QSS（Qt Style Sheets），扁平化设计 |
| 平台 | 仅 Windows 10/11，DPI 适配 100%/125%/150% |
| 字体 | 微软雅黑（中文）+ Segoe UI（英文/数字），系统自带 |
| 窗口模型 | 主窗口可缩放，最小 800x600，推荐 1280x800 |
| 不支持 | macOS/Linux、移动端、深色模式（首版） |
| 图标 | 内嵌 SVG/PNG，不依赖系统主题图标 |

---

## 3. 设计系统

### 3.1 色彩规范

#### 3.1.1 主色（品牌紫）

品牌紫作为应用主色调，用于导航栏选中态、主按钮、进度条进行中状态、强调元素。

| 色阶 | HEX | RGB | 使用场景 |
|---|---|---|---|
| Purple-50 | `#F5F0FF` | 245,240,255 | 主色背景（选中行底色） |
| Purple-100 | `#E6D9FF` | 230,217,255 | 悬浮态背景 |
| Purple-300 | `#B388FF` | 179,136,255 | 边框高亮 |
| **Purple-500（主色）** | `#7C3AED` | 124,58,237 | 主按钮、导航选中、进度条 |
| Purple-600 | `#6D28D9` | 109,40,217 | 主按钮按下态 |
| Purple-700 | `#5B21B6` | 91,33,182 | 主按钮禁用态深色 |

**主色使用规则**：
- 一个页面中主色元素不超过 3 处，避免视觉泛滥
- 主色用于"用户主动操作"的按钮，不用于信息展示
- 文字与主色背景对比度 ≥ 4.5:1（白字 #FFFFFF on Purple-500 通过 WCAG AA）

#### 3.1.2 功能色

| 语义 | 色名 | HEX | RGB | 使用场景 |
|---|---|---|---|---|
| 成功 | Success-Green | `#10B981` | 16,185,129 | 完成、有效、Cookie 状态绿点 |
| 失败 | Error-Red | `#EF4444` | 239,68,68 | 失败、失效、删除按钮、错误提示 |
| 警告 | Warning-Yellow | `#F59E0B` | 245,158,11 | 未测试、重试中、需注意 |
| 信息 | Info-Blue | `#3B82F6` | 59,130,246 | 提示信息、链接、辅助说明 |

**功能色使用规则**：
- 功能色仅用于状态指示，不作为装饰色
- 同一状态在不同位置颜色必须一致
- 红/绿不作为唯一区分手段（色盲友好，配合文字/图标）

#### 3.1.3 中性色

| 色名 | HEX | RGB | 使用场景 |
|---|---|---|---|
| BG-Base | `#FFFFFF` | 255,255,255 | 主背景 |
| BG-Gray | `#F9FAFB` | 249,250,251 | 次背景、卡片底色 |
| BG-Hover | `#F3F4F6` | 243,244,246 | 列表项 hover 底色 |
| BG-Selected | `#F5F0FF` | 245,240,255 | 选中项底色（主色 5% 透明） |
| Border-Light | `#E5E7EB` | 229,231,235 | 分隔线、输入框边框 |
| Border-Default | `#D1D5DB` | 209,213,219 | 卡片边框 |
| Text-Primary | `#111827` | 17,24,39 | 主文字（标题、正文） |
| Text-Secondary | `#6B7280` | 107,114,128 | 次文字（说明、辅助） |
| Text-Disabled | `#9CA3AF` | 156,163,175 | 禁用文字 |
| Text-OnPrimary | `#FFFFFF` | 255,255,255 | 主色背景上的文字 |

**对比度验证**（WCAG AA 标准 ≥ 4.5:1）：
- Text-Primary on BG-Base：16.1:1 ✓
- Text-Secondary on BG-Base：4.6:1 ✓
- Text-OnPrimary on Purple-500：5.9:1 ✓
- Text-Disabled on BG-Base：2.9:1（仅用于禁用态，符合例外条款）

### 3.2 字体规范

#### 3.2.1 字体族

```css
font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif;
```

- **首选**：微软雅黑 UI（Windows 10/11 系统自带，渲染清晰）
- **英文/数字回退**：Segoe UI（Windows 系统字体）
- **最终回退**：sans-serif

#### 3.2.2 字号层级

| 层级 | Token | 字号 | 行高 | 字重 | 使用场景 |
|---|---|---|---|---|---|
| H1 | font-display | 24px | 32px | 600 | 页面主标题（如"下载任务"） |
| H2 | font-h2 | 20px | 28px | 600 | 区块标题 |
| H3 | font-h3 | 16px | 24px | 600 | 卡片标题、分组标题 |
| Body | font-body | 14px | 22px | 400 | 正文（默认字号） |
| Body-Medium | font-body-medium | 14px | 22px | 500 | 强调正文 |
| Caption | font-caption | 12px | 18px | 400 | 辅助文字、时间戳、说明 |
| Button | font-button | 14px | 20px | 500 | 按钮文字 |
| Label | font-label | 13px | 20px | 500 | 表单标签 |

#### 3.2.3 字重

| Token | 字重值 | 使用场景 |
|---|---|---|
| weight-regular | 400 | 默认正文 |
| weight-medium | 500 | 按钮、标签、强调正文 |
| weight-semibold | 600 | 标题 |

**QSS 字体声明**：
```css
* {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 14px;
    font-weight: 400;
    color: #111827;
}
```

### 3.3 间距规范

#### 3.3.1 基准间距单元

采用 **8px 基准网格系统**，所有间距为 4 的倍数，确保视觉节奏一致。

| Token | 值 | 使用场景 |
|---|---|---|
| space-xs | 4px | 图标与文字间距、紧凑内边距 |
| space-sm | 8px | 组件内边距、相邻元素间距 |
| space-md | 12px | 列表项内边距、卡片内边距 |
| space-lg | 16px | 区块内边距、卡片间距 |
| space-xl | 24px | 区块间距、页面分组间距 |
| space-2xl | 32px | 页面顶部/底部留白 |

#### 3.3.2 应用规则

| 场景 | 间距 |
|---|---|
| 页面左右边距 | 24px (space-xl) |
| 页面顶部边距 | 24px (space-xl) |
| 区块之间垂直间距 | 24px (space-xl) |
| 卡片内边距 | 16px (space-lg) |
| 列表项内边距 | 12px (space-md) |
| 按钮内边距（水平） | 16px (space-lg) |
| 按钮内边距（垂直） | 8px (space-sm) |
| 输入框内边距 | 8px 12px |
| 图标与相邻文字 | 8px (space-sm) |

### 3.4 圆角规范

| Token | 值 | 使用场景 |
|---|---|---|
| radius-sm | 4px | 按钮、输入框、标签、徽章 |
| radius-md | 6px | 小卡片、下拉框 |
| radius-lg | 8px | 卡片、列表项、弹窗内元素 |
| radius-xl | 12px | 弹窗、对话框 |
| radius-full | 9999px | 圆形头像、状态指示灯、胶囊按钮 |

**QSS 圆角声明**：
```css
/* 按钮 */
QPushButton { border-radius: 4px; }
/* 输入框 */
QLineEdit, QPlainTextEdit, QTextEdit { border-radius: 4px; }
/* 卡片 */
QFrame#card { border-radius: 8px; }
/* 弹窗 */
QDialog { border-radius: 12px; }
```

> 注意：Qt 的 QSS 对 `border-radius` 支持有限，部分容器需配合 `QGraphicsDropShadowEffect` 或自定义 `paintEvent` 实现真实圆角。

### 3.5 图标规范

#### 3.5.1 图标类型与来源

| 类型 | 格式 | 来源 | 说明 |
|---|---|---|---|
| 导航图标 | SVG | Material Icons / Feather Icons | 线性风格，stroke-width 1.5 |
| 操作图标 | SVG | Material Icons | 暂停/播放/删除/测试等 |
| 状态图标 | PNG | 自绘 | 8px 圆点指示灯 |
| 应用图标 | ICO | 自绘 | 256x256，多尺寸打包 |

#### 3.5.2 图标尺寸

| 用途 | 尺寸 |
|---|---|
| 导航栏图标 | 20x20 px |
| 按钮内图标 | 16x16 px |
| 列表项操作图标 | 16x16 px |
| 状态指示灯 | 8x8 px（圆形） |
| 缩略图 | 64x64 px（任务列表）/ 48x48 px（解析结果） |
| 弹窗大图标 | 32x32 px |

#### 3.5.3 图标颜色

| 场景 | 颜色 |
|---|---|
| 默认图标 | Text-Secondary `#6B7280` |
| 选中态图标 | Purple-500 `#7C3AED` |
| 危险操作图标 | Error-Red `#EF4444` |
| 成功状态图标 | Success-Green `#10B981` |
| 按钮内图标 | 跟随按钮文字色 |

### 3.6 阴影规范

| Token | 阴影值 | 使用场景 |
|---|---|---|
| shadow-sm | `0 1px 2px rgba(0,0,0,0.05)` | 卡片默认 |
| shadow-md | `0 4px 6px rgba(0,0,0,0.08)` | 卡片 hover、下拉菜单 |
| shadow-lg | `0 10px 20px rgba(0,0,0,0.10)` | 弹窗、对话框 |
| shadow-xl | `0 20px 40px rgba(0,0,0,0.15)` | 全局遮罩下的弹窗 |

**Qt 实现说明**：
Qt 通过 `QGraphicsDropShadowEffect` 实现阴影，需在代码中设置：
```python
# 伪代码，仅说明参数
effect = QGraphicsDropShadowEffect()
effect.setBlurRadius(20)
effect.setColor(QColor(0, 0, 0, 25))  # 透明度 10%
effect.setOffset(0, 4)
widget.setGraphicsEffect(effect)
```

> QSS 本身不支持 `box-shadow`，阴影必须通过 `QGraphicsDropShadowEffect` 实现。文档中标注的阴影值是设计期望，实现时按上述映射转换。

---

## 4. 组件规范

### 4.1 导航栏组件

**结构**：左侧固定垂直导航栏，宽度 200px，图标在上、文字在下的卡片式布局（或图标在左、文字在右的列表式布局）。

**布局规格**：
- 宽度：200px（固定，不可缩放）
- 高度：撑满主窗口
- 背景：`#FFFFFF`
- 右边框：1px solid `#E5E7EB`
- 顶部 Logo 区域：高 64px，居中显示应用图标 + 名称
- 导航项：高 44px，左对齐图标(20x20) + 文字(14px)，水平间距 12px
- 底部：版本号文字（12px，Text-Disabled）

**导航项状态**：

| 状态 | 背景 | 文字色 | 图标色 | 左侧指示条 |
|---|---|---|---|---|
| 默认 | 透明 | `#6B7280` | `#6B7280` | 无 |
| Hover | `#F3F4F6` | `#111827` | `#111827` | 无 |
| 选中 | `#F5F0FF` | `#7C3AED` | `#7C3AED` | 3px `#7C3AED` |

**QSS 代码**：
```css
QFrame#navBar {
    background-color: #FFFFFF;
    border-right: 1px solid #E5E7EB;
}

QLabel#navLogo {
    font-size: 16px;
    font-weight: 600;
    color: #7C3AED;
    padding: 16px 20px;
}

QPushButton#navItem {
    text-align: left;
    padding: 12px 20px;
    border: none;
    border-left: 3px solid transparent;
    background-color: transparent;
    color: #6B7280;
    font-size: 14px;
    font-weight: 400;
}

QPushButton#navItem:hover {
    background-color: #F3F4F6;
    color: #111827;
}

QPushButton#navItem:checked {
    background-color: #F5F0FF;
    color: #7C3AED;
    border-left: 3px solid #7C3AED;
    font-weight: 500;
}

QLabel#navVersion {
    color: #9CA3AF;
    font-size: 12px;
    padding: 12px 20px;
}
```

**导航项清单**：
1. 下载任务（icon: download）
2. 链接抓取（icon: link）
3. Cookie 配置（icon: key）
4. 设置（icon: settings）

### 4.2 按钮

#### 4.2.1 按钮类型

| 类型 | 用途 | 默认背景 | 默认文字 |
|---|---|---|---|
| 主按钮（Primary） | 主要操作（开始下载、保存） | `#7C3AED` | `#FFFFFF` |
| 次按钮（Secondary） | 辅助操作（取消、导入） | `#FFFFFF` | `#111827` |
| 危险按钮（Danger） | 破坏性操作（删除、清空） | `#EF4444` | `#FFFFFF` |
| 文本按钮（Text） | 弱化操作（取消、跳过） | 透明 | `#6B7280` |

#### 4.2.2 尺寸

- 高度：32px（标准）/ 28px（紧凑）/ 40px（大）
- 内边距：水平 16px，垂直 8px
- 圆角：4px
- 字号：14px，字重 500

#### 4.2.3 各状态规格

**主按钮**：
| 状态 | 背景 | 文字 | 边框 |
|---|---|---|---|
| 默认 | `#7C3AED` | `#FFFFFF` | 无 |
| Hover | `#6D28D9` | `#FFFFFF` | 无 |
| 按下 | `#5B21B6` | `#FFFFFF` | 无 |
| 禁用 | `#E5E7EB` | `#9CA3AF` | 无 |
| Loading | `#7C3AED` + spinner | `#FFFFFF` | 无 |

**次按钮**：
| 状态 | 背景 | 文字 | 边框 |
|---|---|---|---|
| 默认 | `#FFFFFF` | `#111827` | 1px `#D1D5DB` |
| Hover | `#F9FAFB` | `#111827` | 1px `#7C3AED` |
| 按下 | `#F3F4F6` | `#111827` | 1px `#7C3AED` |
| 禁用 | `#F9FAFB` | `#9CA3AF` | 1px `#E5E7EB` |

**危险按钮**：
| 状态 | 背景 | 文字 | 边框 |
|---|---|---|---|
| 默认 | `#EF4444` | `#FFFFFF` | 无 |
| Hover | `#DC2626` | `#FFFFFF` | 无 |
| 按下 | `#B91C1C` | `#FFFFFF` | 无 |
| 禁用 | `#FCA5A5` | `#FFFFFF` | 无 |

**文本按钮**：
| 状态 | 背景 | 文字 |
|---|---|---|
| 默认 | 透明 | `#6B7280` |
| Hover | `#F3F4F6` | `#111827` |
| 按下 | `#E5E7EB` | `#111827` |
| 禁用 | 透明 | `#9CA3AF` |

**QSS 代码**：
```css
/* 主按钮 */
QPushButton#primaryBtn {
    background-color: #7C3AED;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 500;
}
QPushButton#primaryBtn:hover { background-color: #6D28D9; }
QPushButton#primaryBtn:pressed { background-color: #5B21B6; }
QPushButton#primaryBtn:disabled {
    background-color: #E5E7EB;
    color: #9CA3AF;
}

/* 次按钮 */
QPushButton#secondaryBtn {
    background-color: #FFFFFF;
    color: #111827;
    border: 1px solid #D1D5DB;
    border-radius: 4px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 500;
}
QPushButton#secondaryBtn:hover {
    background-color: #F9FAFB;
    border-color: #7C3AED;
}
QPushButton#secondaryBtn:pressed { background-color: #F3F4F6; }
QPushButton#secondaryBtn:disabled {
    background-color: #F9FAFB;
    color: #9CA3AF;
    border-color: #E5E7EB;
}

/* 危险按钮 */
QPushButton#dangerBtn {
    background-color: #EF4444;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 500;
}
QPushButton#dangerBtn:hover { background-color: #DC2626; }
QPushButton#dangerBtn:pressed { background-color: #B91C1C; }
QPushButton#dangerBtn:disabled {
    background-color: #FCA5A5;
    color: #FFFFFF;
}

/* 文本按钮 */
QPushButton#textBtn {
    background-color: transparent;
    color: #6B7280;
    border: none;
    border-radius: 4px;
    padding: 8px 12px;
    font-size: 14px;
}
QPushButton#textBtn:hover {
    background-color: #F3F4F6;
    color: #111827;
}
QPushButton#textBtn:pressed { background-color: #E5E7EB; }
QPushButton#textBtn:disabled { color: #9CA3AF; }
```

### 4.3 进度条

**类型**：水平进度条，用于任务下载进度。

**规格**：
- 高度：6px（细条）/ 8px（标准）
- 圆角：3px（两端全圆角）
- 轨道颜色：`#E5E7EB`
- 进度颜色：根据状态变化

**状态颜色**：
| 状态 | 进度颜色 | 文字 |
|---|---|---|
| 下载中（downloading） | `#7C3AED` 品牌紫 | 紫色百分比 |
| 已完成（completed） | `#10B981` 绿色 | "完成" |
| 失败（failed） | `#EF4444` 红色 | "失败" |
| 暂停（paused） | `#9CA3AF` 灰色 | "已暂停" |
| 等待中（pending） | `#D1D5DB` 浅灰 | "等待中" |

**动画效果**：
- 下载中：进度条增长有 200ms 缓动过渡（ease-out）
- 完成时：从紫色渐变到绿色（300ms）
- 失败时：从当前颜色闪一下红色（100ms 闪烁 1 次）
- 暂停时：进度条停止增长，颜色变灰（无动画）

**QSS 代码**：
```css
QProgressBar {
    background-color: #E5E7EB;
    border: none;
    border-radius: 3px;
    text-align: center;
    color: #6B7280;
    font-size: 12px;
    min-height: 8px;
    max-height: 8px;
}

QProgressBar::chunk {
    border-radius: 3px;
    background-color: #7C3AED;
}

/* 完成态（通过 setProperty + style refresh 切换） */
QProgressBar[state="completed"]::chunk { background-color: #10B981; }
QProgressBar[state="failed"]::chunk { background-color: #EF4444; }
QProgressBar[state="paused"]::chunk { background-color: #9CA3AF; }
```

> 说明：Qt QSS 不支持基于 `::chunk` 的属性选择器嵌套，实际实现需通过 `QProgressBar.setProperty("state", "completed")` 后调用 `style().unpolish(widget)` + `polish(widget)` 刷新，并使用上述选择器。或直接在代码中用 `setStyleSheet` 切换。

### 4.4 输入框

#### 4.4.1 单行文本框（QLineEdit）

**规格**：
- 高度：32px
- 内边距：8px 12px
- 圆角：4px
- 字号：14px

**状态**：
| 状态 | 背景 | 边框 | 文字 |
|---|---|---|---|
| 默认 | `#FFFFFF` | 1px `#D1D5DB` | `#111827` |
| Focus | `#FFFFFF` | 1px `#7C3AED` + 阴影 | `#111827` |
| 错误 | `#FEF2F2` | 1px `#EF4444` | `#111827` |
| 禁用 | `#F9FAFB` | 1px `#E5E7EB` | `#9CA3AF` |

**Focus 阴影**：`0 0 0 3px rgba(124,58,237,0.15)`（通过 `QGraphicsDropShadowEffect` 实现）

**QSS 代码**：
```css
QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 4px;
    padding: 8px 12px;
    color: #111827;
    font-size: 14px;
    selection-background-color: #E6D9FF;
    selection-color: #111827;
}

QLineEdit:focus {
    border: 1px solid #7C3AED;
}

QLineEdit[error="true"] {
    background-color: #FEF2F2;
    border: 1px solid #EF4444;
}

QLineEdit:disabled {
    background-color: #F9FAFB;
    border: 1px solid #E5E7EB;
    color: #9CA3AF;
}
```

#### 4.4.2 多行文本框（QPlainTextEdit）

用于链接抓取页粘贴多行链接。

**规格**：
- 最小高度：120px
- 内边距：12px
- 圆角：4px
- 字号：14px
- 行高：22px
- 支持 Tab 缩进：否（Tab 切换焦点）

**状态**：同单行文本框。

**占位符文字**（placeholder）：
- 颜色：`#9CA3AF`
- 示例："在此粘贴抖音链接，每行一个\n支持视频链接、图文链接、用户主页链接"

**QSS 代码**：
```css
QPlainTextEdit {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 4px;
    padding: 12px;
    color: #111827;
    font-size: 14px;
    line-height: 22px;
}

QPlainTextEdit:focus {
    border: 1px solid #7C3AED;
}

QPlainTextEdit[error="true"] {
    border: 1px solid #EF4444;
}
```

### 4.5 列表项

#### 4.5.1 任务行（TaskItemWidget）

**布局**：水平排列 [缩略图] [信息区] [进度区] [操作区]

**规格**：
- 高度：72px（默认）/ 96px（失败态含错误提示行）
- 内边距：12px
- 间距：缩略图与信息区 12px，信息区与进度区 16px，进度区与操作区 16px

**元素**：
- 缩略图：64x64px，圆角 4px，占位图灰色 `#E5E7EB`
- 信息区：标题(14px,600) + 作者·日期·时长(12px,400,Secondary)
- 进度区：进度条(宽 200px,高 6px) + 百分比文字(12px)
- 操作区：暂停/继续按钮(32x32,图标按钮)

**状态**：
| 状态 | 背景 | 左边框 |
|---|---|---|
| 默认 | `#FFFFFF` | 无 |
| Hover | `#F9FAFB` | 无 |
| 选中 | `#F5F0FF` | 3px `#7C3AED` |
| 失败 | `#FEF2F2` | 3px `#EF4444` |
| 完成 | `#FFFFFF` | 无（进度条绿色已表达） |

**失败态扩展**：行下方显示红色小字"失败原因：xxx"，行高扩展到 96px。

**QSS 代码**：
```css
QFrame#taskItem {
    background-color: #FFFFFF;
    border-bottom: 1px solid #F3F4F6;
    padding: 12px;
}

QFrame#taskItem:hover { background-color: #F9FAFB; }

QFrame#taskItem[selected="true"] {
    background-color: #F5F0FF;
    border-left: 3px solid #7C3AED;
}

QFrame#taskItem[status="failed"] {
    background-color: #FEF2F2;
    border-left: 3px solid #EF4444;
}

QLabel#taskTitle {
    font-size: 14px;
    font-weight: 600;
    color: #111827;
}

QLabel#taskMeta {
    font-size: 12px;
    color: #6B7280;
}

QLabel#taskFailReason {
    font-size: 12px;
    color: #EF4444;
    padding-top: 4px;
}
```

#### 4.5.2 Cookie 行

**布局**：[状态灯] [标签] [状态文字] [最后使用时间] [测试按钮] [删除按钮]

**规格**：
- 高度：48px
- 内边距：12px 16px
- 间距：各元素间 16px

**元素**：
- 状态指示灯：8x8px 圆形（见 4.6）
- 标签：14px，500
- 状态文字：12px，Secondary
- 最后使用时间：12px，Secondary
- 测试按钮：次按钮，28px 高
- 删除按钮：图标按钮，16x16 红色图标

**QSS 代码**：
```css
QFrame#cookieItem {
    background-color: #FFFFFF;
    border-bottom: 1px solid #F3F4F6;
    padding: 12px 16px;
}

QFrame#cookieItem:hover { background-color: #F9FAFB; }

QLabel#cookieLabel {
    font-size: 14px;
    font-weight: 500;
    color: #111827;
}

QLabel#cookieStatus {
    font-size: 12px;
    color: #6B7280;
}

QLabel#cookieLastUsed {
    font-size: 12px;
    color: #9CA3AF;
}
```

#### 4.5.3 解析结果行

**布局**：[勾选框] [缩略图] [标题] [作者] [类型标签] [时长/图片数]

**规格**：
- 高度：56px
- 内边距：8px 12px

**元素**：
- 勾选框：16x16px
- 缩略图：48x48px，圆角 4px
- 标题：14px,500，最多 1 行省略
- 作者：12px,Secondary
- 类型标签：见 4.7
- 时长/图片数：12px,Secondary

**QSS 代码**：
```css
QFrame#resultItem {
    background-color: #FFFFFF;
    border-bottom: 1px solid #F3F4F6;
    padding: 8px 12px;
}

QFrame#resultItem:hover { background-color: #F9FAFB; }

QFrame#resultItem[selected="true"] { background-color: #F5F0FF; }
```

### 4.6 状态指示灯

**用途**：Cookie 状态指示。

**规格**：
- 尺寸：8x8px
- 形状：圆形
- 颜色：
  - 绿点（valid）：`#10B981`
  - 红点（invalid）：`#EF4444`
  - 黄点（untested）：`#F59E0B`

**实现**：用 QLabel + QSS 圆角实现，或自绘 QWidget。

**QSS 代码**：
```css
QLabel#statusDot {
    min-width: 8px;
    max-width: 8px;
    min-height: 8px;
    max-height: 8px;
    border-radius: 4px;
    background-color: #10B981;  /* 默认绿色 */
}

QLabel#statusDot[state="valid"] { background-color: #10B981; }
QLabel#statusDot[state="invalid"] { background-color: #EF4444; }
QLabel#statusDot[state="untested"] { background-color: #F59E0B; }
```

### 4.7 标签/徽章

**用途**：类型标签（视频/图文/长视频）。

**规格**：
- 高度：20px
- 内边距：2px 8px
- 圆角：4px
- 字号：12px，字重 500

**类型颜色**：
| 类型 | 背景 | 文字 |
|---|---|---|
| 视频 | `#E6D9FF` | `#6D28D9` |
| 图文 | `#DBEAFE` | `#1D4ED8` |
| 长视频 | `#FED7AA` | `#C2410C` |

**QSS 代码**：
```css
QLabel#tagVideo {
    background-color: #E6D9FF;
    color: #6D28D9;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 500;
}

QLabel#tagImageSet {
    background-color: #DBEAFE;
    color: #1D4ED8;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 500;
}

QLabel#tagLongVideo {
    background-color: #FED7AA;
    color: #C2410C;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 500;
}
```

### 4.8 弹窗/对话框

#### 4.8.1 添加 Cookie 弹窗

**结构**：模态对话框，标题 + 表单 + 操作按钮。

**规格**：
- 宽度：480px
- 内边距：24px
- 圆角：12px
- 阴影：shadow-lg
- 标题：18px,600
- 标签：13px,500
- 输入框：见 4.4
- 按钮区：右对齐，主按钮 + 次按钮

**布局**：
```
[标题: 添加 Cookie]
[说明文字（12px,Secondary）]
[标签输入框]
[Cookie 内容多行文本框（高 120px）]
[错误提示区（默认隐藏）]
[取消]                [测试并保存]
```

**QSS 代码**：
```css
QDialog#addCookieDialog {
    background-color: #FFFFFF;
    border-radius: 12px;
}

QLabel#dialogTitle {
    font-size: 18px;
    font-weight: 600;
    color: #111827;
}

QLabel#dialogDesc {
    font-size: 12px;
    color: #6B7280;
    padding: 4px 0 12px 0;
}

QLabel#fieldLabel {
    font-size: 13px;
    font-weight: 500;
    color: #374151;
    padding-top: 8px;
}

QLabel#dialogError {
    font-size: 12px;
    color: #EF4444;
    padding: 8px 0;
}
```

#### 4.8.2 错误弹窗

**结构**：图标 + 标题 + 描述 + 操作按钮。

**布局**：
```
[错误图标 32x32]  [标题: 下载失败]
                  [描述文字（14px,Secondary）]
                  [下一步建议（13px,Secondary）]
                  
                                  [复制详情] [重试] [关闭]
```

**规格**：
- 宽度：440px
- 内边距：24px
- 图标颜色：`#EF4444`
- 标题：16px,600
- 描述：14px,400
- "复制详情"为文本按钮，"重试"为主按钮，"关闭"为次按钮

#### 4.8.3 确认弹窗

**用途**：危险操作前确认（清空已完成、删除 Cookie）。

**布局**：
```
[警告图标 32x32]  [标题: 确认清空已完成任务？]
                  [描述: 将永久删除 N 条已完成任务，此操作不可撤销。]
                  
                              [取消]  [确认清空（危险按钮）]
```

**规格**：
- 宽度：400px
- 内边距：24px
- 图标颜色：`#F59E0B`（警告黄）
- 确认按钮使用危险按钮样式

### 4.9 滑块

**用途**：并发下载数设置（1-10）。

**规格**：
- 高度：轨道 4px，滑块 16x16px
- 宽度：撑满可用空间
- 圆角：轨道 2px，滑块全圆角
- 颜色：
  - 已填充轨道：`#7C3AED`
  - 未填充轨道：`#E5E7EB`
  - 滑块：`#FFFFFF` + 1px `#7C3AED` 边框
  - 滑块 hover：边框 `#6D28D9` + 阴影

**伴随元素**：
- 左侧标签："并发下载数"（14px,500）
- 右侧数值显示：当前值（16px,600,Primary 色）

**QSS 代码**：
```css
QSlider::groove:horizontal {
    height: 4px;
    background: #E5E7EB;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background: #7C3AED;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #FFFFFF;
    border: 1px solid #7C3AED;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    border: 2px solid #6D28D9;
}
```

### 4.10 折叠面板

**用途**：Cookie 教程展开/收起。

**结构**：标题栏（含展开图标）+ 内容区（展开时显示）。

**规格**：
- 标题栏高度：44px
- 内边距：12px 16px
- 展开图标：16x16，向下箭头（展开后旋转 180° 向上）
- 内容区背景：`#F9FAFB`
- 内容区内边距：16px 24px
- 动画：展开/收起 200ms 高度过渡

**QSS 代码**：
```css
QFrame#collapsibleHeader {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 4px;
    padding: 12px 16px;
}

QFrame#collapsibleHeader:hover { background-color: #F9FAFB; }

QLabel#collapsibleTitle {
    font-size: 14px;
    font-weight: 500;
    color: #111827;
}

QFrame#collapsibleContent {
    background-color: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-top: none;
    border-radius: 0 0 4px 4px;
    padding: 16px 24px;
}
```

### 4.11 Toast 提示

**用途**：轻量操作反馈（已复制、已加入队列、设置已保存）。

**规格**：
- 位置：窗口底部居中，距底部 24px
- 高度：40px
- 内边距：12px 16px
- 圆角：4px
- 背景：`#111827`（深色）
- 文字：`#FFFFFF`，14px
- 图标：16x16，白色
- 显示时长：2.5 秒
- 动画：从底部滑入（200ms ease-out），淡出（200ms）

**类型**：
| 类型 | 图标 | 用途 |
|---|---|---|
| 成功 | check-circle | 操作成功 |
| 信息 | info-circle | 一般提示 |
| 警告 | alert-circle | 需注意 |

**QSS 代码**：
```css
QFrame#toast {
    background-color: #111827;
    border-radius: 4px;
    padding: 12px 16px;
}

QLabel#toastText {
    color: #FFFFFF;
    font-size: 14px;
}

QLabel#toastIcon {
    color: #FFFFFF;
}
```

> Toast 实现需自定义 `QFrame` + `QPropertyAnimation`，QSS 仅提供视觉样式。

---

## 5. 页面高保真原型

### 5.1 主窗口框架

**整体布局**：左侧导航栏（200px）+ 右侧内容区（自适应）+ 底部状态栏（32px）。

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  [─][□][×]                                                                  │ ← 标题栏 32px
├──────────────┬───────────────────────────────────────────────────────────────┤
│              │  下载任务                                          [刷新]     │ ← 页面标题区 56px
│  [ icon ]    │                                                              │
│  Douyin      ├───────────────────────────────────────────────────────────────┤
│  Catcher     │                                                              │
│              │                                                              │
│  ┌────────┐  │                                                              │
│  │▼ 下载  │  │                                                              │
│  │  任务  │  │                                                              │
│  └────────┘  │              右侧内容区（随导航切换）                          │
│  ┌────────┐  │                                                              │
│  │  链接  │  │                  高度：撑满主窗口                              │
│  │  抓取  │  │                  宽度：主窗口宽度 - 200px                      │
│  └────────┘  │                                                              │
│  ┌────────┐  │                                                              │
│  │ Cookie │  │                                                              │
│  │  配置  │  │                                                              │
│  └────────┘  │                                                              │
│  ┌────────┐  │                                                              │
│  │  设置  │  │                                                              │
│  └────────┘  │                                                              │
│              │                                                              │
│              │                                                              │
│              ├───────────────────────────────────────────────────────────────┤
│  v1.0.0      │ 总数 12 · 下载中 2 · 已完成 8 · 失败 2          [日志]      │ ← 状态栏 32px
└──────────────┴───────────────────────────────────────────────────────────────┘
     200px                              自适应（推荐主窗口 1280px - 200px = 1080px）
```

**尺寸标注**：
- 主窗口推荐：1280 x 800
- 主窗口最小：800 x 600
- 标题栏：高 32px（系统原生）
- 导航栏：宽 200px，高 = 主窗口高 - 标题栏 - 状态栏
- 内容区：宽 = 主窗口宽 - 200px，高 = 主窗口高 - 标题栏 - 状态栏 - 页面标题区(56px)
- 状态栏：高 32px
- 页面标题区：高 56px，左右内边距 24px

### 5.2 下载任务页

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  下载任务                                                              [刷新] │ ← 56px 标题区
├──────────────────────────────────────────────────────────────────────────────┤
│  [全部暂停] [全部开始] [清空已完成]              搜索[          ] [🔍]       │ ← 48px 工具栏
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────┐  ┌─────────────────────────────────┐  ┌────────────┐  ┌────┐      │
│  │      │  │ 美丽的海边日落                  │  │ ▓▓▓▓░░░░░  │  │ ⏸ │      │ ← 任务行 72px
│  │ 缩略 │  │ @旅行者 · 2026-07-10 · 15s     │  │    45%     │  │    │      │
│  │  图  │  │ [视频]                          │  │            │  │    │      │
│  └──────┘  └─────────────────────────────────┘  └────────────┘  └────┘      │
│  ┌──────┐  ┌─────────────────────────────────┐  ┌────────────┐  ┌────┐      │
│  │      │  │ 城市夜景合集                    │  │ ▓▓▓▓▓▓▓▓▓▓ │  │ ✅ │      │ ← 完成态
│  │ 缩略 │  │ @摄影师 · 2026-07-09 · 12:30   │  │    完成    │  │    │      │
│  │  图  │  │ [长视频]                        │  │            │  │    │      │
│  └──────┘  └─────────────────────────────────┘  └────────────┘  └────┘      │
│  ┌──────┐  ┌─────────────────────────────────┐  ┌────────────┐  ┌────┐      │
│  │      │  │ 美食教程图集                    │  │ ▓▓▓▓▓░░░░░ │  │ ⏸ │      │
│  │ 缩略 │  │ @美食家 · 2026-07-09 · 9张图   │  │   暂停     │  │    │      │ ← 暂停态
│  │  图  │  │ [图文]                          │  │            │  │    │      │
│  └──────┘  └─────────────────────────────────┘  └────────────┘  └────┘      │
│  ┌──────┐  ┌─────────────────────────────────┐  ┌────────────┐  ┌────┐      │
│  │      │  │ 失败的视频标题                  │  │ ░░░░░░░░░░ │  │ 🔄 │      │ ← 失败态（96px）
│  │ 缩略 │  │ @作者 · 2026-07-08 · 1m20s     │  │   失败     │  │    │      │
│  │  图  │  │ [视频]                          │  │            │  │    │      │
│  └──────┘  └─────────────────────────────────┘  └────────────┘  └────┘      │
│            └─⚠ 失败原因：Cookie 已失效，请更新 Cookie                          │ ← 错误提示行
│                                                                              │
│  ┌──────┐  ┌─────────────────────────────────┐  ┌────────────┐  ┌────┐      │
│  │      │  │ 等待下载的视频                  │  │ ░░░░░░░░░░ │  │ ⏸ │      │ ← 等待态
│  │ 缩略 │  │ @作者 · 2026-07-08 · 30s       │  │  等待中    │  │    │      │
│  │  图  │  │ [视频]                          │  │            │  │    │      │
│  └──────┘  └─────────────────────────────────┘  └────────────┘  └────┘      │
│                                                                              │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ 总数 5 · 下载中 1 · 已完成 1 · 失败 1 · 暂停 1 · 等待 1          [导出日志] │ ← 状态栏 32px
└──────────────────────────────────────────────────────────────────────────────┘
```

**元素尺寸标注**：
- 任务行总高：72px（默认）/ 96px（失败态）
- 任务行内边距：12px
- 缩略图：64 x 64px
- 缩略图与信息区间距：12px
- 信息区：标题(14px) + 元信息(12px) + 类型标签(20px)
- 进度条区：宽 200px，进度条高 6px，百分比文字 12px
- 操作按钮：32 x 32px
- 各区间距：16px

**交互说明**：
| 操作 | 行为 |
|---|---|
| 单击任务行 | 选中该行（高亮） |
| 双击任务行 | 打开任务详情（含完整元数据） |
| 右键任务行 | 弹出菜单：暂停/继续、重试、打开所在文件夹、复制链接、删除 |
| 点击暂停按钮 | 暂停/继续该任务（按钮图标切换） |
| 点击重试按钮（失败态） | 重新加入下载队列 |
| 点击"全部暂停" | 暂停所有 downloading 状态的任务 |
| 点击"全部开始" | 继续所有 paused 状态的任务 |
| 点击"清空已完成" | 弹确认弹窗 → 清空 completed 状态的任务 |
| 搜索框输入 | 实时过滤标题/作者 |
| Ctrl+A | 全选任务列表 |
| Delete 键 | 删除选中的任务（弹确认） |

### 5.3 链接抓取页

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  链接抓取                                                                     │ ← 56px 标题区
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────┐  ┌──────────┐     │
│  │ 在此粘贴抖音链接，每行一个                            │  │ 导入文件 │     │ ← 输入区
│  │ 支持视频链接、图文链接、用户主页链接                  │  └──────────┘     │
│  │                                                        │                    │
│  │ https://v.douyin.com/xxxxxxx/                          │                    │
│  │ https://www.douyin.com/video/123456                    │                    │
│  │ https://www.douyin.com/user/xxxxx                      │                    │
│  │                                                        │                    │
│  └──────────────────────────────────────────────────────┘                    │
│                                                                              │
│                                              [开始解析]                      │ ← 48px 操作行
├──────────────────────────────────────────────────────────────────────────────┤
│  ⚠ 检测到用户主页链接，已展开过滤栏                                          │ ← 提示行（可选）
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ 类型: [全部 ▼]  数量上限: [50]  时间段: [2026-01-01] 至 [2026-07-11] │    │ ← 过滤栏（主页链接时显示）
│  └──────────────────────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────────────────┤
│  ☑ 全选                                         已选 3 / 共 5 项            │ ← 列表头
├──────────────────────────────────────────────────────────────────────────────┤
│  ☑  ┌──────┐  美丽的海边日落            @旅行者      [视频]    15s          │
│     │ 缩略 │                                                              │
│     │  图  │                                                              │
│     └──────┘                                                              │
│  ☑  ┌──────┐  城市夜景合集                @摄影师     [长视频]  12:30       │
│     │ 缩略 │                                                              │
│     │  图  │                                                              │
│     └──────┘                                                              │
│  ☐  ┌──────┐  美食教程图集                @美食家      [图文]    9张图       │
│     │ 缩略 │                                                              │
│     │  图  │                                                              │
│     └──────┘                                                              │
│  ☑  ┌──────┐  另一个视频                  @作者        [视频]    30s        │
│     │ 缩略 │                                                              │
│     │  图  │                                                              │
│     └──────┘                                                              │
│  ☐  ┌──────┐  旅行vlog                    @旅行者      [长视频]  5:20       │
│     │ 缩略 │                                                              │
│     │  图  │                                                              │
│     └──────┘                                                              │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  下载目录: D:\Downloads\DouyinCatcher  [浏览...]         [开始下载 (3)]     │ ← 底部操作栏 56px
└──────────────────────────────────────────────────────────────────────────────┘
```

**过滤栏展开效果**：
当解析的链接中检测到用户主页链接时，过滤栏从无到有展开显示，展开动画 200ms 向下滑入。过滤栏包含：
- 类型下拉：全部 / 视频 / 图文 / 长视频
- 数量上限：数字输入框（默认 50，范围 1-500）
- 时间段：起止日期选择器（QDateTimeEdit）

**元素尺寸标注**：
- 输入框：宽撑满 - 100px（导入文件按钮），高 120px
- 导入文件按钮：宽 100px，高 120px（与输入框等高）
- 开始解析按钮：主按钮，高 36px
- 过滤栏：高 48px，内边距 12px 16px
- 列表项：高 56px，缩略图 48x48px
- 底部操作栏：高 56px
- "开始下载"按钮：主按钮，显示已选数量

**交互说明**：
| 操作 | 行为 |
|---|---|
| 粘贴链接 | 自动识别每行一个链接 |
| 点击"导入文件" | 弹出文件选择器，支持 .txt 文件 |
| 点击"开始解析" | loading 状态（按钮变 loading + 禁用），解析完成后结果列表显示 |
| 勾选/取消勾选 | 实时更新"已选 N / 共 M 项"和"开始下载"按钮数字 |
| 点击"全选" | 勾选/取消所有结果项 |
| 点击"开始下载" | 将选中项加入下载队列，跳转到下载任务页，Toast 提示"已加入队列" |
| 检测到主页链接 | 自动展开过滤栏，显示提示行 |
| 修改过滤条件 | 重新过滤结果列表（本地过滤，无需重新请求） |
| 双击结果项 | 打开作品详情预览（封面 + 标题 + 作者） |

### 5.4 Cookie 配置页

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Cookie 配置                                                                  │ ← 56px 标题区
├──────────────────────────────────────────────────────────────────────────────┤
│  [+ 添加 Cookie]  [全部测试]  [教程 ▼]                                       │ ← 48px 操作栏
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ●  账号1     有效      最后使用: 2026-07-11 10:30        [测试] [🗑]        │ ← Cookie 行 48px
│  ●  账号2     失效      最后使用: 2026-07-10 18:22        [测试] [🗑]        │
│  ●  账号3     未测试    最后使用: -                       [测试] [🗑]        │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  ▼ Cookie 获取教程                                                            │ ← 折叠面板标题 44px
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  步骤 1：打开抖音网页版                                              │    │
│  │  浏览器访问 https://www.douyin.com 并登录                            │    │
│  │  ┌────────────────────────────────────────────────┐                  │    │
│  │  │                                                  │                  │    │
│  │  │              [step1.png 截图]                   │                  │    │
│  │  │                                                  │                  │    │
│  │  │     浏览器打开 douyin.com 已登录状态              │                  │    │
│  │  │                                                  │                  │    │
│  │  └────────────────────────────────────────────────┘                  │    │
│  │                                                                       │    │
│  │  ─────────────────────────────────────────────────────────────────    │    │
│  │  步骤 2：打开开发者工具                                              │    │
│  │  按 F12 键，切到"Network"（网络）标签                                │    │
│  │  ┌────────────────────────────────────────────────┐                  │    │
│  │  │              [step2.png 截图]                   │                  │    │
│  │  └────────────────────────────────────────────────┘                  │    │
│  │                                                                       │    │
│  │  ...（步骤 3-7 类似结构）                                            │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ 共 3 个 Cookie · 有效 1 · 失效 1 · 未测试 1                                   │ ← 状态栏
└──────────────────────────────────────────────────────────────────────────────┘
```

**添加 Cookie 弹窗线框图**：
```
┌──────────────────────────────────────────────────────────┐
│  添加 Cookie                                       [×]   │ ← 标题 + 关闭
├──────────────────────────────────────────────────────────┤
│  请粘贴从浏览器复制的 Cookie，并为其设置一个标签便于识别。│ ← 说明文字
│                                                          │
│  标签                                                    │
│  ┌──────────────────────────────────────────────────┐    │
│  │ 例如：账号1                                       │    │ ← 标签输入框
│  └──────────────────────────────────────────────────┘    │
│                                                          │
│  Cookie 内容                                             │
│  ┌──────────────────────────────────────────────────┐    │
│  │                                                    │    │
│  │  在此粘贴 Cookie 字符串...                         │    │ ← 多行文本框
│  │                                                    │    │
│  │                                                    │    │
│  └──────────────────────────────────────────────────┘    │
│  ⚠ Cookie 格式不正确，请确认复制了完整的 Cookie 值       │ ← 错误提示（条件显示）
│                                                          │
│                          [取消]   [测试并保存]           │ ← 操作按钮
└──────────────────────────────────────────────────────────┘
       宽 480px                          高自适应
```

**教程展开后图文布局**：
- 每个步骤：标题(16px,600) + 说明文字(14px) + 截图(800x450,圆角 8px)
- 步骤之间：分隔线 1px `#E5E7EB`，上下间距 24px
- 截图下方：可选说明文字(12px,Secondary)
- 教程内容区最大高度：撑满可用空间，内部滚动

**元素尺寸标注**：
- Cookie 行：高 48px，状态灯 8px，操作按钮 28px 高
- 折叠面板标题：高 44px
- 教程截图：宽 800px（或撑满内容区），高按 16:9 比例（450px）

**交互说明**：
| 操作 | 行为 |
|---|---|
| 点击"+ 添加 Cookie" | 弹出添加 Cookie 弹窗 |
| 点击"全部测试" | 依次测试所有未失效 Cookie，状态灯实时更新 |
| 点击"教程 ▼" | 展开/收起教程折叠面板 |
| 点击单个 Cookie 的"测试" | 测试该 Cookie，loading 状态 + 结果反馈 |
| 点击"🗑"删除 | 弹确认弹窗 → 删除该 Cookie |
| 点击状态灯 | 无操作（仅展示） |
| 弹窗"测试并保存" | 先测试 Cookie 有效性，有效则保存，无效显示错误 |
| 弹窗"取消" | 关闭弹窗，不保存 |

### 5.5 设置页

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  设置                                                                         │ ← 56px 标题区
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  下载设置                                                                    │ ← 分组标题
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  下载目录                                                              │    │
│  │  D:\Downloads\DouyinCatcher                              [浏览...]   │    │
│  │                                                                       │    │
│  │  ─────────────────────────────────────────────────────────────────    │    │
│  │  并发下载数                                            3              │    │
│  │  ●─────○○○○○○○○○                                                    │    │ ← 滑块 1-10
│  │  1                              10                                    │    │
│  │                                                                       │    │
│  │  ─────────────────────────────────────────────────────────────────    │    │
│  │  单文件分块大小                                    1 MB  [▼]          │    │ ← 下拉框
│  │                                                                       │    │
│  │  ─────────────────────────────────────────────────────────────────    │    │
│  │  失败重试次数                                          3 次（固定）  │    │ ← 禁用态
│  │                                                                       │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  元数据设置                                                                  │ ← 分组标题
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  元数据保存格式                                                       │    │
│  │  ☑ JSON    ☐ CSV                                                     │    │ ← 勾选框
│  │                                                                       │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  日志与反馈                                                                  │ ← 分组标题
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  日志位置  %APPDATA%\DouyinCatcher\logs\app.log                       │    │
│  │                                                       [导出日志]     │    │
│  │                                                                       │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  关于                                                                        │ ← 分组标题
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  抖音抓取器 (Douyin_Catcher)                                          │    │
│  │  版本: v1.0.0                                                         │    │
│  │  设计参考: Evil0ctal/Douyin_TikTok_Download_API                       │    │
│  │                                              [检查更新]  [开源仓库]   │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**元素尺寸标注**：
- 分组卡片：圆角 8px，边框 1px `#E5E7EB`，内边距 16px 20px
- 分组间距：24px
- 分组标题：16px,600，下方间距 12px
- 设置项行高：48px（含分隔线）
- 滑块：宽 300px

**交互说明**：
| 操作 | 行为 |
|---|---|
| 点击"浏览..." | 弹出文件夹选择器，选择下载目录 |
| 拖动滑块 | 实时显示数值（1-10），释放后保存 |
| 修改分块大小下拉 | 选项 512KB / 1MB / 2MB / 4MB，选择后立即保存 |
| 勾选 JSON/CSV | 至少保留一个，立即保存 |
| 点击"导出日志" | 弹出保存文件对话框，将日志打包导出 |
| 点击"检查更新" | 检查 GitHub Release（首版暂不实现，按钮禁用） |
| 点击"开源仓库" | 打开浏览器跳转 GitHub 仓库 |
| 下载目录为空 | 输入框红色边框 + 错误提示"请选择下载目录" |

### 5.6 首次引导流程

首次启动时全屏引导，步骤指示器在顶部。

#### 5.6.1 欢迎页

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│                                                                              │
│                                                                              │
│                          ┌────────────┐                                      │
│                          │            │                                      │
│                          │  应用图标  │                                      │
│                          │  128x128   │                                      │
│                          │            │                                      │
│                          └────────────┘                                      │
│                                                                              │
│                     欢迎使用抖音抓取器                                        │ ← 24px,600
│                                                                              │
│              一款让你轻松下载抖音视频的桌面工具                               │ ← 14px,Secondary
│              无需命令行，配置 Cookie 后即可一键下载                           │
│                                                                              │
│                          ● ○ ○ ○                                             │ ← 步骤指示器
│                                                                              │
│                              [开始使用]                                      │ ← 主按钮
│                                                                              │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### 5.6.2 目录设置页

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  步骤 1：设置下载目录                                                         │ ← 20px,600
│                                                                              │
│  选择视频文件保存的位置，建议使用默认目录。                                   │ ← 14px,Secondary
│                                                                              │
│  ┌────────────────────────────────────────────────────────────┐  ┌────────┐ │
│  │ C:\Users\你的用户名\Downloads\DouyinCatcher                 │  │ 浏览.. │ │
│  └────────────────────────────────────────────────────────────┘  └────────┘ │
│                                                                              │
│  ℹ 默认目录为系统下载文件夹下的 DouyinCatcher 子文件夹，可随时在设置中修改。 │ ← 12px,信息蓝
│                                                                              │
│                              ● ● ○ ○                                         │
│                                                                              │
│                       [上一步]   [下一步]                                    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### 5.6.3 Cookie 配置引导页

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  步骤 2：配置 Cookie                                                          │ ← 20px,600
│                                                                              │
│  抖音需要登录态才能访问视频数据，请按教程获取 Cookie。                        │ ← 14px,Secondary
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  Cookie 获取教程（简版）                                              │    │
│  │  1. 浏览器打开 douyin.com 并登录                                      │    │
│  │  2. 按 F12 打开开发者工具 → Network 标签                              │    │
│  │  3. 刷新页面，点任意请求，复制 Request Headers 里的 Cookie 值         │    │
│  │  完整教程见 Cookie 配置页 →                                          │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Cookie 内容                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │                                                                        │    │
│  │  在此粘贴 Cookie 字符串...                                             │    │
│  │                                                                        │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  标签                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ 账号1                                                                 │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│                              [测试 Cookie]                                   │ ← 测试通过后变 [完成]
│                              ● ● ● ○                                         │
│                                                                              │
│                      [上一步]   [跳过，稍后配置]                            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### 5.6.4 完成页

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│                                                                              │
│                                                                              │
│                          ┌────────────┐                                      │
│                          │            │                                      │
│                          │  ✅ 完成   │                                      │
│                          │  64x64     │                                      │
│                          │            │                                      │
│                          └────────────┘                                      │
│                                                                              │
│                       配置完成！                                              │ ← 24px,600
│                                                                              │
│              现在可以开始下载抖音视频了                                       │ ← 14px,Secondary
│              前往"链接抓取"页粘贴链接即可开始                                 │
│                                                                              │
│                              ● ● ● ●                                         │
│                                                                              │
│                              [进入应用]                                      │ ← 主按钮
│                                                                              │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**引导流程交互说明**：
| 步骤 | 操作 |
|---|---|
| 欢迎页 | 点击"开始使用"进入目录设置 |
| 目录设置 | 点击"浏览"选择目录，或保留默认；点击"下一步"进入 Cookie 配置 |
| Cookie 配置 | 粘贴 Cookie → 点"测试 Cookie" → 测试通过后按钮变"完成" → 点击进入完成页；可"跳过" |
| 完成页 | 点击"进入应用"跳转到下载任务页 |
| 步骤指示器 | 显示当前步骤，点击已完成的步骤可回退 |
| 跳过 Cookie | 完成页提示"Cookie 未配置，部分功能不可用，请稍后在 Cookie 配置页完成配置" |

---

## 6. 交互设计规范

### 6.1 状态流转

任务从 `pending` → `downloading` → `completed`/`failed` 的视觉变化：

| 状态 | 任务行外观 | 进度条 | 操作按钮 | 文字提示 |
|---|---|---|---|---|
| pending（等待中） | 默认白色，左边框无 | 浅灰 `#D1D5DB`，0% | 暂停按钮（禁用） | "等待中" |
| downloading（下载中） | 默认白色 | 品牌紫 `#7C3AED`，动态增长 | 暂停按钮 ⏸ | "45%" 实时百分比 |
| paused（已暂停） | 默认白色，左边框浅灰 | 灰色 `#9CA3AF`，停在当前位置 | 继续按钮 ▶ | "已暂停" |
| completed（已完成） | 默认白色 | 绿色 `#10B981`，100% | 打开文件夹按钮 📁 | "完成" |
| failed（失败） | 红色底 `#FEF2F2`，左边框红 | 红色 `#EF4444`，停在失败位置 | 重试按钮 🔄 | "失败" + 下方红色原因 |

**状态切换动画**：
- pending → downloading：进度条从浅灰变紫色（300ms 过渡）
- downloading → completed：进度条从紫色渐变到绿色（500ms），完成后任务行轻微高亮闪烁一次
- downloading → failed：进度条闪红（100ms 闪烁），任务行背景变红（200ms）
- downloading → paused：进度条颜色变灰（200ms），增长停止

### 6.2 Loading 状态设计

| 场景 | Loading 表现 | 可取消 |
|---|---|---|
| 解析链接 | "开始解析"按钮变为 loading 状态（图标转圈 + 文字"解析中..."），按钮禁用；结果列表区显示骨架屏 | 是，按钮变"取消" |
| 测试 Cookie | 该 Cookie 行的"测试"按钮变 loading；状态灯变黄色闪烁 | 是 |
| 全部测试 Cookie | 每行依次测试，状态灯依次变化；顶部显示"正在测试 1/3..."进度 | 是 |
| 主页抓取 | 解析按钮 loading + 结果列表区显示"正在抓取主页作品...已获取 N 条"，底部进度条显示整体进度 | 是 |
| 添加 Cookie 保存 | "测试并保存"按钮 loading | 否（快速操作） |

**Loading 视觉规范**：
- Spinner：16x16px 圆形旋转，颜色跟随按钮文字色
- 骨架屏：灰色块 `#E5E7EB`，带从左到右的微光扫过动画（1.5s 循环）
- 文字提示：14px，Secondary 色

### 6.3 空状态设计

| 场景 | 空状态表现 |
|---|---|
| 无任务（下载任务页） | 居中显示：图标(64x64 灰色) + "还没有下载任务" + "前往链接抓取页添加链接" + [去添加链接]主按钮 |
| 无 Cookie（Cookie 配置页） | 居中显示：图标(64x64) + "还没有配置 Cookie" + "配置 Cookie 后才能下载视频" + [+ 添加 Cookie]主按钮 + [查看教程]文本按钮 |
| 解析结果为空 | 居中显示：图标(48x48) + "没有解析到结果" + "请检查链接是否正确" |
| 搜索无结果 | 居中显示："没有找到匹配的任务" |

**空状态规格**：
- 图标：64x64px（或 48x48），颜色 `#D1D5DB`
- 标题：16px,500,Text-Primary
- 说明：14px,400,Text-Secondary
- 操作按钮：主按钮，居中

### 6.4 错误状态设计

#### 6.4.1 任务行级错误
- 任务行背景变红 `#FEF2F2`
- 左边框 3px 红色 `#EF4444`
- 行下方显示红色小字："失败原因：{人话解释}"
- 操作按钮变"重试"图标
- 不打断其他任务

#### 6.4.2 全局错误弹窗
触发场景：
- 所有 Cookie 都失效
- 磁盘空间不足
- 数据库损坏

弹窗结构：
```
┌──────────────────────────────────────────────────┐
│  ⚠  所有 Cookie 已失效                            │
│                                                  │
│  当前所有 Cookie 都已失效，无法继续下载。          │
│  请前往 Cookie 配置页更新 Cookie。                │
│                                                  │
│                              [去配置]  [关闭]    │
└──────────────────────────────────────────────────┘
```

#### 6.4.3 输入错误
- 输入框边框变红 `#EF4444`
- 输入框下方显示红色小字错误提示
- 不弹窗
- 示例：链接格式错误 → "无法识别该链接，请确认是抖音视频/主页链接"

**错误文案规范**：
- 用"人话"，避免技术术语
- 包含两部分：发生了什么 + 用户该做什么
- 示例："Cookie 已失效，抖音需要重新登录验证。请按教程重新获取 Cookie。"

### 6.5 动画规范

| 元素 | 动画 | 时长 | 缓动 |
|---|---|---|---|
| 进度条增长 | 宽度变化 | 200ms | ease-out |
| 进度条完成变色 | 背景色紫→绿 | 500ms | linear |
| 任务行新增 | 从上方滑入 + 淡入 | 250ms | ease-out |
| 任务行删除 | 高度收缩 + 淡出 | 200ms | ease-in |
| 列表项 hover | 背景色变化 | 150ms | ease |
| 弹窗显示 | 缩放 0.95→1 + 淡入 | 200ms | ease-out |
| 弹窗关闭 | 缩放 1→0.95 + 淡出 | 150ms | ease-in |
| Toast 显示 | 从底部滑入 + 淡入 | 200ms | ease-out |
| Toast 消失 | 淡出 | 200ms | ease-in |
| 折叠面板展开 | 高度展开 | 200ms | ease-out |
| 导航切换 | 内容区淡入 | 150ms | ease |
| 状态灯切换 | 颜色变化 | 200ms | ease |

**动画原则**：
- 总时长不超过 300ms（除进度条变色）
- 同一时间不超过 2 个动画并行
- 尊重系统"减少动画"设置（Windows: SystemParametersInfo）

### 6.6 快捷键

| 快捷键 | 作用 | 适用页面 |
|---|---|---|
| `Ctrl+A` | 全选任务 | 下载任务页 |
| `Delete` | 删除选中任务（弹确认） | 下载任务页 |
| `Space` | 暂停/继续选中任务 | 下载任务页 |
| `Ctrl+P` | 全部暂停 | 下载任务页 |
| `Ctrl+S` | 全部开始 | 下载任务页 |
| `Ctrl+V` | 粘贴链接到输入框 | 链接抓取页 |
| `Enter` | 开始解析（输入框有焦点时） | 链接抓取页 |
| `Ctrl+Enter` | 开始下载 | 链接抓取页 |
| `Esc` | 关闭弹窗 / 取消选中 | 全局 |
| `F5` | 刷新任务列表 | 下载任务页 |
| `Ctrl+,` | 跳转设置页 | 全局 |
| `Alt+1` | 切换到下载任务页 | 全局 |
| `Alt+2` | 切换到链接抓取页 | 全局 |
| `Alt+3` | 切换到 Cookie 配置页 | 全局 |
| `Alt+4` | 切换到设置页 | 全局 |

**快捷键提示**：按钮 hover 时 tooltip 显示快捷键，如"全部暂停 (Ctrl+P)"。

---

## 7. 响应式设计

### 7.1 窗口尺寸

| 场景 | 尺寸 | 说明 |
|---|---|---|
| 最小尺寸 | 800 x 600 | 低于此尺寸无法正常显示，窗口不可再缩小 |
| 推荐尺寸 | 1280 x 800 | 最佳视觉体验 |
| 大屏尺寸 | 1920 x 1080 | 内容区自适应扩大，任务列表显示更多行 |

### 7.2 自适应规则

| 组件 | 自适应行为 |
|---|---|
| 导航栏 | 固定 200px，不随窗口缩放 |
| 内容区 | 宽度 = 窗口宽 - 200px，自适应 |
| 任务行 | 宽度撑满内容区，进度条区宽度自适应（最小 150px） |
| 解析结果行 | 宽度撑满，标题区省略号截断 |
| 输入框（链接抓取页） | 宽度撑满 |
| 弹窗 | 固定宽度，居中显示，不随窗口缩放 |

### 7.3 任务列表滚动行为

- 任务列表区域：垂直滚动
- 滚动条样式：细条（8px宽），hover 时变 12px
- 滚动条颜色：`#D1D5DB`，hover `#9CA3AF`
- 滚动平滑：启用像素级平滑滚动
- 横向不滚动（任务行内容自适应宽度）

**QSS 滚动条代码**：
```css
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #D1D5DB;
    border-radius: 4px;
    min-height: 32px;
}

QScrollBar::handle:vertical:hover { background: #9CA3AF; }

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical { height: 0; }

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #D1D5DB;
    border-radius: 4px;
    min-width: 32px;
}

QScrollBar::handle:horizontal:hover { background: #9CA3AF; }
```

### 7.4 侧边栏折叠

当窗口宽度 < 1000px 时，侧边栏自动折叠为图标模式（仅显示图标，宽度 56px）：

```
┌────┬─────────────────────────────────────────────────────────────────────────┐
│    │  下载任务                                                        [刷新] │
│[📥]├─────────────────────────────────────────────────────────────────────────┤
│    │                                                                         │
│[🔗]│                                                                         │
│    │              内容区宽度增加 144px                                       │
│[🔑]│                                                                         │
│    │                                                                         │
│[⚙️]│                                                                         │
└────┴─────────────────────────────────────────────────────────────────────────┘
 56px
```

- 折叠动画：宽度 200px → 56px（200ms ease）
- 图标居中，tooltip 显示完整名称
- 点击图标切换页面
- 窗口宽度 ≥ 1000px 时自动展开

---

## 8. 无障碍设计

### 8.1 色彩对比度

所有文字与背景的色彩对比度需满足 WCAG 2.1 AA 标准：

| 组合 | 对比度 | 标准 | 结果 |
|---|---|---|---|
| Text-Primary on BG-Base | 16.1:1 | ≥ 4.5:1 | ✓ |
| Text-Secondary on BG-Base | 4.6:1 | ≥ 4.5:1 | ✓ |
| Text-OnPrimary on Purple-500 | 5.9:1 | ≥ 4.5:1 | ✓ |
| Text-Disabled on BG-Base | 2.9:1 | ≥ 3:1（大文字） | ✓（仅禁用态） |
| 白字 on Error-Red | 4.0:1 | ≥ 4.5:1 | ⚠ 接近边界，按钮文字加粗弥补 |
| 白字 on Success-Green | 2.5:1 | — | ✗ 不作为文字背景，仅作进度条/指示灯 |

**色盲友好**：
- 状态指示不仅靠颜色，同时配合文字（如"有效/失效/未测试"）
- 失败任务除红色背景外，左边框 + 错误图标 + 错误文字三重提示
- 视频/图文/长视频标签除颜色外，有文字标签

### 8.2 键盘导航支持

| 键位 | 行为 |
|---|---|
| `Tab` | 在可聚焦元素间正向切换 |
| `Shift+Tab` | 反向切换 |
| `Enter` / `Space` | 激活当前聚焦的按钮/勾选框 |
| `Esc` | 关闭弹窗 / 取消操作 |
| 方向键 ↑↓ | 在列表项间切换 |
| 方向键 ←→ | 在标签页/滑块间切换 |

**焦点指示器**：
- 所有可聚焦元素必须有可见的焦点轮廓
- 焦点轮廓：2px Purple-300 `#B388FF`，offset 2px
- 不要使用 `outline: none` 隐藏焦点

**QSS 焦点样式**：
```css
QPushButton:focus {
    outline: 2px solid #B388FF;
    outline-offset: 2px;
}

QLineEdit:focus,
QPlainTextEdit:focus {
    outline: none;  /* 用 border-color 表达焦点 */
}
```

### 8.3 文字大小可调节

- 支持 Windows 系统字体缩放（DPI 100%/125%/150%）
- 所有文字使用 `px` 单位，Qt 自动按 DPI 缩放
- 不使用固定像素的图片文字
- 测试 125%/150% DPI 下布局不溢出、不截断

---

## 9. Cookie 教程截图规范

### 9.1 截图需求清单

共需 7 张截图，对应 Cookie 获取教程的 7 个步骤：

| 步骤 | 截图文件 | 内容描述 |
|---|---|---|
| 步骤 1 | `step1.png` | 浏览器打开 douyin.com 已登录状态的页面 |
| 步骤 2 | `step2.png` | 按 F12 打开开发者工具后，Network（网络）标签的界面 |
| 步骤 3 | `step3.png` | 按 F5 刷新后，Network 列表出现多条请求的界面 |
| 步骤 4 | `step4.png` | 点击某条 douyin.com 请求后，右侧出现 Headers 面板的界面 |
| 步骤 5 | `step5.png` | Headers 面板里 Cookie 字段被高亮/选中的界面 |
| 步骤 6 | `step6.png` | 应用添加 Cookie 弹窗，Cookie 已粘贴进文本框的状态 |
| 步骤 7 | `step7.png` | 测试通过后显示"Cookie 有效"的状态 |

### 9.2 截图尺寸要求

| 项目 | 要求 |
|---|---|
| 推荐尺寸 | 800 x 600 px（4:3）或 800 x 450 px（16:9） |
| 最小尺寸 | 640 x 360 px |
| 格式 | PNG（无损） |
| 文件大小 | 单张 ≤ 500KB |
| DPI | 96 DPI（屏幕截图标准） |

### 9.3 截图标注要求

为帮助用户快速定位关键区域，截图需进行标注：

| 步骤 | 标注要求 |
|---|---|
| step1 | 用红色矩形框高亮浏览器地址栏的 douyin.com URL |
| step2 | 用红色矩形框高亮开发者工具顶部的 "Network" 标签 |
| step3 | 用红色矩形框高亮 Network 请求列表区域 |
| step4 | 用红色矩形框高亮右侧 Headers 面板 |
| step5 | 用红色矩形框高亮 Request Headers 中的 `Cookie:` 字段 |
| step6 | 用红色矩形框高亮应用弹窗中的 Cookie 文本框 |
| step7 | 用红色矩形框高亮"Cookie 有效"状态指示灯 |

**标注样式**：
- 标注框：2px 红色 `#EF4444` 实线矩形
- 标注框圆角：4px
- 可选箭头：从标注框指向关键元素（红色 2px 线条）
- 不遮挡关键信息

### 9.4 图片存放路径

截图文件存放在项目资源目录：

```
ui/assets/cookie_tutorial/
├── step1.png    # 浏览器打开 douyin.com 已登录状态
├── step2.png    # F12 打开后 Network 标签
├── step3.png    # 刷新后 Network 列表出现请求
├── step4.png    # 点击请求后 Headers 面板
├── step5.png    # Cookie 字段高亮
├── step6.png    # 应用添加 Cookie 弹窗
└── step7.png    # Cookie 有效状态
```

**打包说明**：截图随应用打包（PyInstaller `--add-data "ui/assets;ui/assets"`），无需用户单独下载。

**截图提供方式**：截图由开发者在真实浏览器环境中录制，提交前需：
- 涂抹/模糊化个人账号信息（用户名、头像、Cookie 内容）
- 确保截图不含真实有效 Cookie 值（用占位文字 "Cookie值..." 替代）

---

## 10. 附录

### 附录 A. QSS 全局样式表草案

以下为 `ui/assets/style.qss` 全局样式表草案，可直接作为开发起点：

```css
/* ===== 全局重置 ===== */
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 14px;
    font-weight: 400;
    color: #111827;
}

QWidget {
    background-color: #FFFFFF;
    color: #111827;
}

/* ===== 主窗口 ===== */
QMainWindow {
    background-color: #FFFFFF;
}

/* ===== 导航栏 ===== */
QFrame#navBar {
    background-color: #FFFFFF;
    border-right: 1px solid #E5E7EB;
    min-width: 200px;
    max-width: 200px;
}

QLabel#navLogo {
    font-size: 16px;
    font-weight: 600;
    color: #7C3AED;
    padding: 20px 20px 24px 20px;
}

QPushButton#navItem {
    text-align: left;
    padding: 12px 20px;
    border: none;
    border-left: 3px solid transparent;
    background-color: transparent;
    color: #6B7280;
    font-size: 14px;
    font-weight: 400;
    min-height: 44px;
}

QPushButton#navItem:hover {
    background-color: #F3F4F6;
    color: #111827;
}

QPushButton#navItem:checked {
    background-color: #F5F0FF;
    color: #7C3AED;
    border-left: 3px solid #7C3AED;
    font-weight: 500;
}

QLabel#navVersion {
    color: #9CA3AF;
    font-size: 12px;
    padding: 16px 20px;
}

/* ===== 页面标题 ===== */
QLabel#pageTitle {
    font-size: 24px;
    font-weight: 600;
    color: #111827;
    padding: 16px 24px;
}

/* ===== 按钮 ===== */
QPushButton {
    background-color: #FFFFFF;
    color: #111827;
    border: 1px solid #D1D5DB;
    border-radius: 4px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 500;
    min-height: 32px;
}

QPushButton:hover {
    background-color: #F9FAFB;
    border-color: #7C3AED;
}

QPushButton:pressed { background-color: #F3F4F6; }

QPushButton:disabled {
    background-color: #F9FAFB;
    color: #9CA3AF;
    border-color: #E5E7EB;
}

QPushButton#primaryBtn {
    background-color: #7C3AED;
    color: #FFFFFF;
    border: none;
}

QPushButton#primaryBtn:hover { background-color: #6D28D9; }
QPushButton#primaryBtn:pressed { background-color: #5B21B6; }
QPushButton#primaryBtn:disabled {
    background-color: #E5E7EB;
    color: #9CA3AF;
}

QPushButton#dangerBtn {
    background-color: #EF4444;
    color: #FFFFFF;
    border: none;
}

QPushButton#dangerBtn:hover { background-color: #DC2626; }
QPushButton#dangerBtn:pressed { background-color: #B91C1C; }

/* ===== 输入框 ===== */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDateTimeEdit {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 4px;
    padding: 8px 12px;
    color: #111827;
    font-size: 14px;
    selection-background-color: #E6D9FF;
    selection-color: #111827;
}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QComboBox:focus, QSpinBox:focus, QDateTimeEdit:focus {
    border: 1px solid #7C3AED;
}

QLineEdit:disabled, QPlainTextEdit:disabled {
    background-color: #F9FAFB;
    color: #9CA3AF;
}

QLineEdit[error="true"], QPlainTextEdit[error="true"] {
    border: 1px solid #EF4444;
    background-color: #FEF2F2;
}

/* QComboBox 下拉 */
QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    width: 12px;
    height: 12px;
}

QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 4px;
    padding: 4px;
    selection-background-color: #F5F0FF;
    selection-color: #7C3AED;
}

/* ===== 进度条 ===== */
QProgressBar {
    background-color: #E5E7EB;
    border: none;
    border-radius: 3px;
    text-align: center;
    color: #6B7280;
    font-size: 12px;
    min-height: 8px;
    max-height: 8px;
}

QProgressBar::chunk {
    border-radius: 3px;
    background-color: #7C3AED;
}

/* ===== 滑块 ===== */
QSlider::groove:horizontal {
    height: 4px;
    background: #E5E7EB;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background: #7C3AED;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #FFFFFF;
    border: 1px solid #7C3AED;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover { border: 2px solid #6D28D9; }

/* ===== 滚动条 ===== */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #D1D5DB;
    border-radius: 4px;
    min-height: 32px;
}

QScrollBar::handle:vertical:hover { background: #9CA3AF; }

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical { height: 0; }

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #D1D5DB;
    border-radius: 4px;
    min-width: 32px;
}

QScrollBar::handle:horizontal:hover { background: #9CA3AF; }

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal { width: 0; }

/* ===== 状态栏 ===== */
QStatusBar {
    background-color: #F9FAFB;
    border-top: 1px solid #E5E7EB;
    color: #6B7280;
    font-size: 12px;
    min-height: 32px;
    max-height: 32px;
    padding: 4px 16px;
}

/* ===== 对话框 ===== */
QDialog {
    background-color: #FFFFFF;
}

QLabel#dialogTitle {
    font-size: 18px;
    font-weight: 600;
    color: #111827;
}

QLabel#dialogDesc {
    font-size: 14px;
    color: #6B7280;
}

QLabel#fieldLabel {
    font-size: 13px;
    font-weight: 500;
    color: #374151;
}

QLabel#errorText {
    font-size: 12px;
    color: #EF4444;
}

/* ===== 卡片 ===== */
QFrame#card {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
}

QFrame#cardHover:hover {
    border-color: #D1D5DB;
}

/* ===== 标签 ===== */
QLabel#tag {
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 500;
}

QLabel#tagVideo { background-color: #E6D9FF; color: #6D28D9; }
QLabel#tagImageSet { background-color: #DBEAFE; color: #1D4ED8; }
QLabel#tagLongVideo { background-color: #FED7AA; color: #C2410C; }

/* ===== 复选框 ===== */
QCheckBox {
    spacing: 8px;
    color: #111827;
    font-size: 14px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #D1D5DB;
    border-radius: 3px;
    background-color: #FFFFFF;
}

QCheckBox::indicator:hover { border-color: #7C3AED; }

QCheckBox::indicator:checked {
    background-color: #7C3AED;
    border-color: #7C3AED;
}

/* ===== 工具提示 ===== */
QToolTip {
    background-color: #111827;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}

/* ===== 菜单 ===== */
QMenu {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 4px;
    padding: 4px;
}

QMenu::item {
    padding: 8px 24px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #F5F0FF;
    color: #7C3AED;
}

QMenu::separator {
    height: 1px;
    background-color: #E5E7EB;
    margin: 4px 8px;
}
```

### 附录 B. 图标资源清单

| 图标名称 | 用途 | 尺寸 | 格式 | 路径 |
|---|---|---|---|---|
| `nav_download.svg` | 导航-下载任务 | 20x20 | SVG | `ui/assets/icons/nav_download.svg` |
| `nav_link.svg` | 导航-链接抓取 | 20x20 | SVG | `ui/assets/icons/nav_link.svg` |
| `nav_cookie.svg` | 导航-Cookie 配置 | 20x20 | SVG | `ui/assets/icons/nav_cookie.svg` |
| `nav_settings.svg` | 导航-设置 | 20x20 | SVG | `ui/assets/icons/nav_settings.svg` |
| `icon_pause.svg` | 暂停 | 16x16 | SVG | `ui/assets/icons/icon_pause.svg` |
| `icon_play.svg` | 继续/播放 | 16x16 | SVG | `ui/assets/icons/icon_play.svg` |
| `icon_check.svg` | 完成 | 16x16 | SVG | `ui/assets/icons/icon_check.svg` |
| `icon_retry.svg` | 重试 | 16x16 | SVG | `ui/assets/icons/icon_retry.svg` |
| `icon_delete.svg` | 删除 | 16x16 | SVG | `ui/assets/icons/icon_delete.svg` |
| `icon_folder.svg` | 打开文件夹 | 16x16 | SVG | `ui/assets/icons/icon_folder.svg` |
| `icon_refresh.svg` | 刷新 | 16x16 | SVG | `ui/assets/icons/icon_refresh.svg` |
| `icon_search.svg` | 搜索 | 16x16 | SVG | `ui/assets/icons/icon_search.svg` |
| `icon_plus.svg` | 添加 | 16x16 | SVG | `ui/assets/icons/icon_plus.svg` |
| `icon_test.svg` | 测试 | 16x16 | SVG | `ui/assets/icons/icon_test.svg` |
| `icon_chevron_down.svg` | 折叠展开 | 16x16 | SVG | `ui/assets/icons/icon_chevron_down.svg` |
| `icon_warning.svg` | 警告 | 32x32 | SVG | `ui/assets/icons/icon_warning.svg` |
| `icon_error.svg` | 错误 | 32x32 | SVG | `ui/assets/icons/icon_error.svg` |
| `icon_info.svg` | 信息 | 32x32 | SVG | `ui/assets/icons/icon_info.svg` |
| `icon_success.svg` | 成功 | 32x32 | SVG | `ui/assets/icons/icon_success.svg` |
| `icon_file_import.svg` | 导入文件 | 16x16 | SVG | `ui/assets/icons/icon_file_import.svg` |
| `icon_export.svg` | 导出 | 16x16 | SVG | `ui/assets/icons/icon_export.svg` |
| `icon_copy.svg` | 复制 | 16x16 | SVG | `ui/assets/icons/icon_copy.svg` |
| `icon_link_external.svg` | 外部链接 | 16x16 | SVG | `ui/assets/icons/icon_link_external.svg` |
| `icon_browse.svg` | 浏览 | 16x16 | SVG | `ui/assets/icons/icon_browse.svg` |
| `icon_app.svg` | 应用 Logo | 128x128 | SVG | `ui/assets/icons/icon_app.svg` |
| `icon_empty_task.svg` | 空状态-无任务 | 64x64 | SVG | `ui/assets/icons/icon_empty_task.svg` |
| `icon_empty_cookie.svg` | 空状态-无 Cookie | 64x64 | SVG | `ui/assets/icons/icon_empty_cookie.svg` |
| `icon_empty_result.svg` | 空状态-无结果 | 48x48 | SVG | `ui/assets/icons/icon_empty_result.svg` |
| `thumbnail_placeholder.svg` | 缩略图占位 | 64x64 | SVG | `ui/assets/icons/thumbnail_placeholder.svg` |
| `icon.ico` | 应用图标（多尺寸） | 16/32/48/256 | ICO | `assets/icon.ico` |

**图标风格要求**：
- 线性图标（outline style），stroke-width 1.5px
- 圆角端点（stroke-linecap: round, stroke-linejoin: round）
- 24x24 viewBox 绘制，按需缩放
- 颜色用 `currentColor`，便于 QSS 控制色

**Cookie 教程截图清单**（详见第 9 章）：

| 文件 | 路径 |
|---|---|
| step1.png ~ step7.png | `ui/assets/cookie_tutorial/step1.png` ~ `step7.png` |

---

> **文档结束**
>
> 本规范作为 UI 开发的唯一视觉与交互依据。开发过程中如遇 QSS 无法实现的效果（如阴影、复杂圆角），需与设计组协商替代方案，不得擅自偏离规范。所有视觉变更需更新本文档并标注版本。
