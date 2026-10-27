import { AbsoluteFill } from "remotion";
import { BOTTOM_BAR_HEIGHT } from "./layout";

// 하단 460px 검은 자막 띠.
export const BottomBar: React.FC = () => (
  <AbsoluteFill style={{ top: "auto", bottom: 0, height: BOTTOM_BAR_HEIGHT, backgroundColor: "#000" }} />
);
