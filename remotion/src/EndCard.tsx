import { AbsoluteFill, Img, Sequence, staticFile, useVideoConfig } from "remotion";
import { FONT_FAMILY, HIGHLIGHT_COLOR } from "./layout";

// showEndcard=true일 때 마지막 endcardDurationFrames 동안 투자 면책 고지를 전체 화면으로 표시한다.
// 이 구간은 내레이션이 끝난 뒤에 붙으므로(duration에 포함) 자막·그림을 가리지 않는다. 문구는 props로만 받는다.
export const EndCard: React.FC<{
  text: string;
  ctaText: string;
  showCta: boolean;
  headerLogo: string | null;
  durationFrames: number;
}> = ({ text, ctaText, showCta, headerLogo, durationFrames }) => {
  const { durationInFrames } = useVideoConfig();
  return (
    <Sequence from={durationInFrames - durationFrames} durationInFrames={durationFrames} layout="none">
      <AbsoluteFill
        style={{
          backgroundColor: "#111",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 90,
          padding: 80,
          color: "#fff",
          fontFamily: FONT_FAMILY,
          fontWeight: 700,
          textAlign: "center",
        }}
      >
        {headerLogo ? <Img src={staticFile(headerLogo)} style={{ maxWidth: 760, maxHeight: 200 }} /> : null}
        <div style={{ fontSize: 58, lineHeight: 1.5, whiteSpace: "pre-line", wordBreak: "keep-all" }}>{text}</div>
        {showCta ? <div style={{ fontSize: 56, color: HIGHLIGHT_COLOR }}>{ctaText}</div> : null}
      </AbsoluteFill>
    </Sequence>
  );
};
