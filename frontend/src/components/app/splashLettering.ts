/**
 * 启动页艺术字字形数据 —— "VideoGetTool" 手工单线（monoline）字形。
 *
 * 坐标约定：每个字形使用局部坐标，基线 y=100，大写高 y=0（顶部），
 * x 高 y=44，笔画宽度 9（圆头圆角）。布局时按步进宽度 + 字距横向排列，
 * 由 SplashScreen 通过 <g transform="translate(x,0)"> 落位。
 *
 * 字形风格：几何无衬线单线体，"V" 起笔与 "G / T" 大写呼应 Logo 的
 * 倒三角 / 圆弧语言；"i" 的点以墨滴形式落下。
 */

export interface SplashGlyph {
  /** 步进宽度（本字形墨迹宽度 + 右侧呼吸空间） */
  adv: number;
  /** 连续描边路径（按落笔顺序，逐条延迟绘制）；纯圆弧字形可为空 */
  paths?: string[];
  /** 正圆笔画（d 的碗 / o 的圈），以 pathLength 描边 */
  circles?: { cx: number; cy: number; r: number }[];
  /** 实心墨点（i 的点），下落弹入 */
  dots?: { cx: number; cy: number; r: number }[];
}

export interface SplashGlyphPlacement {
  letter: string;
  /** 落位后的全局 x 平移 */
  x: number;
  glyph: SplashGlyph;
}

/** 字距 */
const WORD_GAP = 13;

const GLYPHS: Record<string, SplashGlyph> = {
  V: {
    adv: 64,
    paths: ["M 2 0 L 32 100 L 62 0"],
  },
  i: {
    adv: 14,
    paths: ["M 7 44 L 7 100"],
    dots: [{ cx: 7, cy: 22, r: 5.5 }],
  },
  d: {
    adv: 58,
    paths: ["M 52 0 L 52 100"],
    circles: [{ cx: 26, cy: 72, r: 26 }],
  },
  e: {
    adv: 58,
    paths: ["M 0 72 L 52 72 A 26 26 0 1 0 46 88.7"],
  },
  o: {
    adv: 58,
    circles: [{ cx: 26, cy: 72, r: 26 }],
  },
  G: {
    adv: 92,
    paths: ["M 76.4 22.5 A 42 48 0 1 0 84 50 L 56 50"],
  },
  t: {
    adv: 48,
    paths: ["M 20 16 L 20 100", "M 0 44 L 42 44"],
  },
  T: {
    adv: 64,
    paths: ["M 0 0 L 64 0", "M 32 0 L 32 100"],
  },
  l: {
    adv: 14,
    paths: ["M 7 0 L 7 100"],
  },
};

function layoutWord(word: string): SplashGlyphPlacement[] {
  const out: SplashGlyphPlacement[] = [];
  let cursor = 0;
  for (const letter of word) {
    const glyph = GLYPHS[letter];
    if (!glyph) throw new Error(`splashLettering: 缺少字形 "${letter}"`);
    out.push({ letter, x: cursor, glyph });
    cursor += glyph.adv + WORD_GAP;
  }
  return out;
}

export const WORD_TEXT = "VideoGetTool";
export const WORD_LAYOUT: SplashGlyphPlacement[] = layoutWord(WORD_TEXT);

/** 全词墨迹总宽度（字距只计入字与字之间），用于托盘/箭头的居中定位 */
export const WORD_WIDTH =
  WORD_LAYOUT.reduce((sum, g) => sum + g.glyph.adv, 0) +
  WORD_GAP * (WORD_LAYOUT.length - 1);

/** 整幅字画的 viewBox（含笔画半径与光晕呼吸空间；底部预留托盘 y=126） */
export const WORD_VIEWBOX = "-8 -14 803 158";
