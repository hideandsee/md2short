import { Composition } from "remotion";
import type { RemotionProps } from "./generated/props";
import { TechExplainer } from "./TechExplainer";
import { defaultProps } from "./defaultProps";

// 1080×1920, 30fps 고정. 길이는 Python이 계산한 props.durationInFrames를 그대로 쓴다.
export const RemotionRoot: React.FC = () => (
  <Composition
    id="TechExplainer"
    component={TechExplainer as unknown as React.FC<Record<string, unknown>>}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={defaultProps.durationInFrames}
    defaultProps={defaultProps as unknown as Record<string, unknown>}
    calculateMetadata={({ props }) => ({
      durationInFrames: (props as unknown as RemotionProps).durationInFrames,
    })}
  />
);
