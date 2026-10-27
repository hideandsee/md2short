/* Generated from md2short.schema.RemotionProps by scripts/gen_types.sh. Do not edit. */

export interface RemotionProps {
  audioFileName: string;
  bgColor: string;
  captionSegments: CaptionSegment[];
  chunkSize: number;
  companyLogoCues: CompanyLogoCue[];
  ctaText: string;
  durationInFrames: number;
  emoticonCues: EmoticonCue[];
  fontFamily: string;
  headerLogo: string | null;
  highlightKeywords: string[];
  numberCards: NumberCard[];
  openingDurationFrames: number;
  openingDurationMs: number;
  openingText: string;
  outroDurationFrames: number;
  showOpening: boolean;
  showOutro: boolean;
  wordsFileName: string;
}
export interface CaptionSegment {
  endFrame: number;
  endMs: number;
  highlightKeyword: string | null;
  index: number;
  startFrame: number;
  startMs: number;
  text: string;
  wordEnd: number;
  wordStart: number;
  words: FramedWord[];
}
export interface FramedWord {
  endFrame: number;
  endMs: number;
  startFrame: number;
  startMs: number;
  text: string;
}
export interface CompanyLogoCue {
  company: string;
  durationFrames: number;
  durationMs: number;
  logoFileName: string;
  startFrame: number;
  startMs: number;
}
export interface EmoticonCue {
  assetKind: "emoticon" | "photo";
  durationFrames: number;
  durationMs: number;
  emoticonFileName: string;
  keyword: string | null;
  primaryVisualSubject: string | null;
  startFrame: number;
  startMs: number;
  visualKeywords: string[];
  visualMode: "emoticon" | "photo";
}
export interface NumberCard {
  durationFrames: number;
  durationMs: number;
  startFrame: number;
  startMs: number;
  text: string;
  wordEnd: number;
  wordStart: number;
}
