import { AbsoluteFill, Img, staticFile } from "remotion";
import { FONT_FAMILY, HEADER_HEIGHT, HEADER_LOGO_HEIGHT, HEADER_SAFE_MARGIN } from "./layout";

// 상단 470px 검은 띠 = safe margin 250px + logo 220px.
// headerLogo가 null이면(img/header_logo.png 없음) 텍스트 워드마크로 대체한다.
export const BrandHeader: React.FC<{ headerLogo: string | null }> = ({ headerLogo }) => (
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
        <Img src={staticFile(headerLogo)} style={{ maxHeight: HEADER_LOGO_HEIGHT - 40, maxWidth: 900 }} />
      ) : (
        <div style={{ color: "#fff", fontFamily: FONT_FAMILY, fontWeight: 700, fontSize: 96, letterSpacing: 4 }}>
          데이브리핑
        </div>
      )}
    </div>
  </AbsoluteFill>
);
