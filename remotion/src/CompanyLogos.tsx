import { AbsoluteFill, Img, Sequence, staticFile } from "remotion";
import type { CompanyLogoCue } from "./generated/props";
import { CONTENT_HEIGHT, CONTENT_TOP } from "./layout";

export const CompanyLogos: React.FC<{ cues: CompanyLogoCue[] }> = ({ cues }) => (
  <AbsoluteFill>
    {cues.map((cue, i) => (
      <Sequence key={i} from={cue.startFrame} durationInFrames={cue.durationFrames} layout="none">
        <Img
          src={staticFile(cue.logoFileName)}
          style={{
            position: "absolute",
            left: 60,
            top: CONTENT_TOP + CONTENT_HEIGHT - 260,
            height: 200,
            maxWidth: 360,
            objectFit: "contain",
            backgroundColor: "rgba(255,255,255,0.9)",
            borderRadius: 24,
            padding: 16,
          }}
        />
      </Sequence>
    ))}
  </AbsoluteFill>
);
