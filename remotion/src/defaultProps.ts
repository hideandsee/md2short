import type { RemotionProps } from "./generated/props";

// Studio 미리보기용 최소 props. 실제 렌더는 항상 --props로 Python이 만든 값을 받는다.
export const defaultProps: RemotionProps = {
  audioFileName: "",
  wordsFileName: "",
  bgColor: "#FFFFFF",
  chunkSize: 14,
  captionSegments: [],
  emoticonCues: [],
  companyLogoCues: [],
  numberCards: [],
  highlightKeywords: [],
  openingText: "",
  openingSubtitle: "",
  openingDurationMs: 0,
  openingDurationFrames: 0,
  showOpening: false,
  ctaText: "",
  showOutro: false,
  outroDurationFrames: 0,
  headerLogo: null,
  openingImage: null,
  fontFamily: "MD2ShortSans",
  durationInFrames: 30,
};
