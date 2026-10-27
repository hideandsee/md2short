import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";
import { FONT_FAMILY, HEADER_HEIGHT, HEADER_LOGO_HEIGHT, HEADER_SAFE_MARGIN } from "./layout";

// 상단 400px 검은 띠 = safe margin 250px + logo 150px.
// headerLogo가 null이면(img/header_logo.png 없음) 텍스트 워드마크로 대체하되,
// 오프닝 박스에 같은 "데이브리핑"이 보이는 동안에는 워드마크를 숨긴다(중복 방지).
export const BrandHeader: React.FC<{ headerLogo: string | null; hideWordmarkUntilFrame: number }> = ({
  headerLogo,
  hideWordmarkUntilFrame,
}) => {
  const frame = useCurrentFrame();
  const showWordmark = frame >= hideWordmarkUntilFrame;
  return (
    <AbsoluteFill style={{ height: HEADER_HEIGHT, backgroundColor: "#000" }}>
      <div
        style={{
          position: "absolute",
          top: HEADER_SAFE_MARGIN,
          height: HEADER_LOGO_HEIGHT,
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {headerLogo ? (
          <Img src={staticFile(headerLogo)} style={{ maxHeight: HEADER_LOGO_HEIGHT - 30, maxWidth: 900 }} />
        ) : showWordmark ? (
          <div style={{ color: "#fff", fontFamily: FONT_FAMILY, fontWeight: 700, fontSize: 80, letterSpacing: 4 }}>
            데이브리핑
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
