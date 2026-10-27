import { AbsoluteFill, Img, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import type { EmoticonCue } from "./generated/props";
import { CONTENT_HEIGHT, CONTENT_TOP } from "./layout";

// cue별 <Sequence>. emoticon은 정사각 contain, photo는 safe content rectangle cover.
const KenBurns: React.FC<{ cue: EmoticonCue; index: number }> = ({ cue, index }) => {
  const frame = useCurrentFrame();
  const zoomIn = index % 2 === 0;
  const scale = interpolate(frame, [0, cue.durationFrames], zoomIn ? [1, 1.06] : [1.06, 1], {
    extrapolateRight: "clamp",
  });
  const photo = cue.assetKind === "photo";
  return (
    <Img
      src={staticFile(cue.emoticonFileName)}
      style={{
        width: photo ? "100%" : "78%",
        height: photo ? "100%" : "78%",
        objectFit: photo ? "cover" : "contain",
        transform: `scale(${scale})`,
      }}
    />
  );
};

export const VisualLayer: React.FC<{ cues: EmoticonCue[] }> = ({ cues }) => (
  <AbsoluteFill style={{ top: CONTENT_TOP, height: CONTENT_HEIGHT, overflow: "hidden" }}>
    {cues.map((cue, i) => (
      <Sequence key={i} from={cue.startFrame} durationInFrames={cue.durationFrames} layout="none">
        <AbsoluteFill style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <KenBurns cue={cue} index={i} />
        </AbsoluteFill>
      </Sequence>
    ))}
  </AbsoluteFill>
);
