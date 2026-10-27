import { AbsoluteFill, Sequence, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { NumberCard as NumberCardCue } from "./generated/props";
import { CONTENT_TOP, FONT_FAMILY } from "./layout";

const Card: React.FC<{ text: string; index: number }> = ({ text, index }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 12 } });
  const tilt = index % 2 === 0 ? -4 : 4;
  return (
    <div
      style={{
        position: "absolute",
        top: CONTENT_TOP + 60,
        right: 60,
        padding: "24px 44px",
        borderRadius: 28,
        backgroundColor: "#FFD400",
        color: "#111",
        fontFamily: FONT_FAMILY,
        fontWeight: 700,
        fontSize: 92,
        boxShadow: "0 12px 30px rgba(0,0,0,0.25)",
        transform: `scale(${pop}) rotate(${tilt * pop}deg)`,
      }}
    >
      {text}
    </div>
  );
};

export const NumberCards: React.FC<{ cards: NumberCardCue[] }> = ({ cards }) => (
  <AbsoluteFill>
    {cards.map((card, i) => (
      <Sequence key={i} from={card.startFrame} durationInFrames={card.durationFrames} layout="none">
        <Card text={card.text} index={i} />
      </Sequence>
    ))}
  </AbsoluteFill>
);
