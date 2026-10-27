import { AbsoluteFill, Audio, staticFile } from "remotion";
import { BottomBar } from "./BottomBar";
import { BrandHeader } from "./BrandHeader";
import { Captions } from "./Captions";
import { CompanyLogos } from "./CompanyLogos";
import { ensureFontsLoaded } from "./Fonts";
import type { RemotionProps } from "./generated/props";
import { CONTENT_HEIGHT, CONTENT_TOP } from "./layout";
import { NumberCards } from "./NumberCard";
import { OpeningBriefing } from "./OpeningBriefing";
import { Outro } from "./Outro";
import { VisualLayer } from "./VisualLayer";

ensureFontsLoaded();

// 합성 루트: props.json을 그대로 그린다. 편집 판단·시간 계산 없음.
export const TechExplainer: React.FC<RemotionProps> = (props) => (
  <AbsoluteFill style={{ backgroundColor: "#000" }}>
    <AbsoluteFill style={{ top: CONTENT_TOP, height: CONTENT_HEIGHT, backgroundColor: props.bgColor }} />
    {props.audioFileName ? <Audio src={staticFile(props.audioFileName)} /> : null}
    <VisualLayer cues={props.emoticonCues} />
    <CompanyLogos cues={props.companyLogoCues} />
    <NumberCards cards={props.numberCards} />
    <BrandHeader headerLogo={props.headerLogo} />
    <BottomBar />
    <Captions segments={props.captionSegments} />
    {props.showOpening ? (
      <OpeningBriefing text={props.openingText} durationFrames={props.openingDurationFrames} />
    ) : null}
    {props.showOutro ? <Outro ctaText={props.ctaText} durationFrames={props.outroDurationFrames} /> : null}
  </AbsoluteFill>
);
