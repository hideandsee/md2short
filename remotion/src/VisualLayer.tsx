import { AbsoluteFill, Img, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import type { EmoticonCue } from "./generated/props";
import { CONTENT_HEIGHT, CONTENT_TOP } from "./layout";

const ORIGINS = ["50% 50%", "30% 40%", "70% 40%", "50% 65%"];

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
        width: photo ? "100%" : "92%",
        height: photo ? "100%" : "92%",
        objectFit: photo ? "cover" : "contain",
        transform: `scale(${scale})`,
        // 같은 그림이 이어질 때 확대 기준점을 바꿔 화면에 변화를 준다(B7)
        transformOrigin: ORIGINS[index % ORIGINS.length],
        // 그림 배경(≈#FCFCFC)을 콘텐츠 흰 배경에 맞춰 사각 테두리가 보이지 않게 한다(B2)
        filter: photo ? undefined : "brightness(1.012)",
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
