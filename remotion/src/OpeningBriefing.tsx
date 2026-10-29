import { AbsoluteFill, Img, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { CONTENT_HEIGHT, CONTENT_TOP, FONT_FAMILY } from "./layout";

// showOpening일 때 [0, openingDurationFrames) 구간에 "YY년 M월 D일\n타이거살구브리핑" 박스 + 아래 hook 한 줄.
export const OpeningBriefing: React.FC<{
  text: string;
  subtitle: string;
  image: string | null;
  durationFrames: number;
}> = ({
  text,
  subtitle,
  image,
  durationFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (frame >= durationFrames) return null;
  const pop = spring({ frame, fps, config: { damping: 14 } });
  return (
    <AbsoluteFill
      style={{
        top: CONTENT_TOP,
        height: CONTENT_HEIGHT,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 48,
      }}
    >
      {image ? (
        <Img
          src={staticFile(image)}
          style={{ width: 420, height: 420, objectFit: "contain", transform: `scale(${0.85 + 0.15 * pop})`, filter: "brightness(1.012)" }}
        />
      ) : null}
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
          // 첫 프레임(썸네일)부터 박스가 보이도록 85%에서 시작해 100%로 커진다.
          transform: `scale(${0.85 + 0.15 * pop})`,
        }}
      >
        {text}
      </div>
      {subtitle ? (
        <div
          style={{
            maxWidth: 960,
            padding: "20px 36px",
            borderRadius: 24,
            backgroundColor: "#FFD400",
            color: "#111",
            fontFamily: FONT_FAMILY,
            fontWeight: 700,
            fontSize: 52,
            lineHeight: 1.3,
            textAlign: "center",
            wordBreak: "keep-all",
            transform: `scale(${0.85 + 0.15 * pop})`,
          }}
        >
          {subtitle}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
