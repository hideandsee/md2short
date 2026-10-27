import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { CaptionSegment } from "./generated/props";
import { BOTTOM_BAR_HEIGHT, FONT_FAMILY, HIGHLIGHT_COLOR } from "./layout";

// 순수 렌더러: 자막 분할·시간 계산은 Python caption_plan.py 몫이다.
// 여기서는 props의 프레임 값으로 현재 segment를 고르고 그리기만 한다.
const fontSizeFor = (chars: number): number => {
  if (chars <= 18) return 72;
  if (chars <= 30) return 62;
  if (chars <= 44) return 54;
  return 46;
};

export const Captions: React.FC<{ segments: CaptionSegment[] }> = ({ segments }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const segment = segments.find((s) => frame >= s.startFrame && frame < s.endFrame);
  if (!segment) return null;
  const fontSize = fontSizeFor(segment.text.length);
  return (
    <AbsoluteFill
      style={{
        top: "auto",
        bottom: 0,
        height: BOTTOM_BAR_HEIGHT,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "0 60px",
      }}
    >
      <div
        style={{
          fontFamily: FONT_FAMILY,
          fontWeight: 700,
          fontSize,
          lineHeight: 1.3,
          color: "#fff",
          textAlign: "center",
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
          wordBreak: "keep-all",
        }}
      >
        {segment.words.map((word, i) => {
          const active = frame >= word.startFrame && frame < word.endFrame;
          const pop = active ? spring({ frame: frame - word.startFrame, fps, durationInFrames: 6 }) : 0;
          const highlighted = segment.highlightKeyword !== null && word.text.includes(segment.highlightKeyword);
          return (
            <span
              key={i}
              style={{
                display: "inline-block",
                marginRight: "0.28em",
                transform: `scale(${1 + 0.08 * pop})`,
                color: highlighted ? HIGHLIGHT_COLOR : "#fff",
              }}
            >
              {word.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
