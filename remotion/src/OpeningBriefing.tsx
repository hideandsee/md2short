import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { CONTENT_HEIGHT, CONTENT_TOP, FONT_FAMILY } from "./layout";

// showOpening일 때 [0, openingDurationFrames) 구간에 "YY년 M월 D일\n데이브리핑" 박스.
export const OpeningBriefing: React.FC<{ text: string; durationFrames: number }> = ({ text, durationFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (frame >= durationFrames) return null;
  const pop = spring({ frame, fps, config: { damping: 14 } });
  return (
    <AbsoluteFill
      style={{ top: CONTENT_TOP, height: CONTENT_HEIGHT, display: "flex", alignItems: "center", justifyContent: "center" }}
    >
      <div
        style={{
          backgroundColor: "#111",
          color: "#fff",
          borderRadius: 40,
          padding: "60px 80px",
          fontFamily: FONT_FAMILY,
          fontWeight: 700,
          fontSize: 104,
          lineHeight: 1.25,
          textAlign: "center",
          whiteSpace: "pre-line",
          transform: `scale(${pop})`,
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};
