import { AbsoluteFill, Sequence, useVideoConfig } from "remotion";
import { FONT_FAMILY } from "./layout";

// showOutro=true일 때만 마지막 outroDurationFrames 동안 구독 CTA overlay.
export const Outro: React.FC<{ ctaText: string; durationFrames: number }> = ({ ctaText, durationFrames }) => {
  const { durationInFrames } = useVideoConfig();
  return (
    <Sequence from={durationInFrames - durationFrames} durationInFrames={durationFrames} layout="none">
      <AbsoluteFill
        style={{
          backgroundColor: "rgba(0,0,0,0.82)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#fff",
          fontFamily: FONT_FAMILY,
          fontWeight: 700,
          fontSize: 88,
          textAlign: "center",
          padding: 80,
        }}
      >
        🐯 {ctaText}
      </AbsoluteFill>
    </Sequence>
  );
};
