import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";
import { FONT_FAMILY } from "./layout";

// Python render.stage_fonts()가 public/font/에 고정 파일명으로 복사한다.
// loadFont는 내부에서 delayRender를 걸어 폰트가 로드되기 전 프레임을 찍지 않는다.
const HANGUL_RANGE = "U+1100-11FF,U+3000-303F,U+3130-318F,U+A960-A97F,U+AC00-D7AF,U+D7B0-D7FF,U+FF00-FFEF";
const LATIN_RANGE =
  "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD";

const faces = [
  { file: "font/regular.woff2", weight: "400", unicodeRange: HANGUL_RANGE },
  { file: "font/regular-latin.woff2", weight: "400", unicodeRange: LATIN_RANGE },
  { file: "font/bold.woff2", weight: "700", unicodeRange: HANGUL_RANGE },
  { file: "font/bold-latin.woff2", weight: "700", unicodeRange: LATIN_RANGE },
];

let started = false;

export const ensureFontsLoaded = (): void => {
  if (started) return;
  started = true;
  for (const face of faces) {
    loadFont({
      family: FONT_FAMILY,
      url: staticFile(face.file),
      weight: face.weight,
      unicodeRange: face.unicodeRange,
      format: "woff2",
    });
  }
};
