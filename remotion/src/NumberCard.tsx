import { AbsoluteFill, Sequence, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { NumberCard as NumberCardCue } from "./generated/props";
import { CONTENT_HEIGHT, CONTENT_TOP, DOWN_COLOR, FONT_FAMILY, UP_COLOR } from "./layout";

// 이미지 상단에 그려진 문구를 가리지 않도록 콘텐츠 영역 하단(자막 띠 바로 위)에 띄운다.
const Card: React.FC<{ card: NumberCardCue; index: number }> = ({ card, index }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 12 } });
  const tilt = index % 2 === 0 ? -3 : 3;
  const color = card.direction === "up" ? UP_COLOR : card.direction === "down" ? DOWN_COLOR : "#111";
  const arrow = card.direction === "up" ? "▲" : card.direction === "down" ? "▼" : "";
  return (
    <div
      style={{
        position: "absolute",
        top: CONTENT_TOP + CONTENT_HEIGHT - 300,
        right: 48,
        padding: "18px 40px 22px",
        borderRadius: 28,
        backgroundColor: "#FFD400",
        color: "#111",
        fontFamily: FONT_FAMILY,
        fontWeight: 700,
        textAlign: "center",
        boxShadow: "0 12px 30px rgba(0,0,0,0.25)",
        transform: `scale(${pop}) rotate(${tilt * pop}deg)`,
        transformOrigin: "bottom right",
      }}
    >
      {card.label ? <div style={{ fontSize: 44, lineHeight: 1.1 }}>{card.label}</div> : null}
      <div style={{ fontSize: 96, lineHeight: 1.1, color }}>
        {arrow ? <span style={{ fontSize: 64, marginRight: 8 }}>{arrow}</span> : null}
        {card.text}
      </div>
    </div>
  );
};

export const NumberCards: React.FC<{ cards: NumberCardCue[] }> = ({ cards }) => (
  <AbsoluteFill>
    {cards.map((card, i) => (
      <Sequence key={i} from={card.startFrame} durationInFrames={card.durationFrames} layout="none">
        <Card card={card} index={i} />
      </Sequence>
    ))}
  </AbsoluteFill>
);
