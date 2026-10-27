// 화면 레이아웃 상수 (docs/architecture.md §2.3).
export const WIDTH = 1080;
export const HEIGHT = 1920;
// 플랫폼 UI가 덮는 상단 250px만 비우고 로고 띠를 줄여 콘텐츠 영역을 넓힌다(review.md #10).
export const HEADER_HEIGHT = 400;
export const HEADER_SAFE_MARGIN = 250;
export const HEADER_LOGO_HEIGHT = 150;
export const BOTTOM_BAR_HEIGHT = 420;
export const CONTENT_TOP = HEADER_HEIGHT;
export const CONTENT_HEIGHT = HEIGHT - HEADER_HEIGHT - BOTTOM_BAR_HEIGHT;
export const FONT_FAMILY = "MD2ShortSans";
export const HIGHLIGHT_COLOR = "#FFD400";
// 한국 증시 관례: 상승 빨강, 하락 파랑
export const UP_COLOR = "#E5322D";
export const DOWN_COLOR = "#1E63D6";
