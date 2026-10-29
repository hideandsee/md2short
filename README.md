# MD2Short

마크다운 1개를 한국어 9:16 숏폼 MP4로 변환하는 로컬 CLI.
설계 문서는 [`docs/README.md`](docs/README.md), 작업 원칙은 [`AGENTS.md`](AGENTS.md) 참조.

```text
markdown → 대본(OpenAI 또는 추출) → ElevenLabs TTS → Scribe words.json
        → 자막·cue 계획(Python) → Remotion 렌더 → QC → output/ret.mp4
```

## 1. 설치

필요: Linux/WSL2 또는 macOS, Node 20+ 와 pnpm, 인터넷(외부 API).

```bash
# 시스템 도구: ffmpeg/ffprobe(길이 측정·QC용). Ubuntu/WSL 예:
sudo apt-get install -y ffmpeg
# Remotion 렌더용 Chrome Headless Shell 라이브러리(없을 때만)
sudo apt-get install -y libnss3 libgbm1 libasound2 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libpango-1.0-0 libcairo2

# uv (Python 패키지 관리자)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Python 의존성 (Python 3.12는 uv가 설치)
uv sync

# Remotion 의존성 + 브라우저
pnpm -C remotion install
pnpm -C remotion exec remotion browser ensure
```

## 2. API 키

```bash
cp .env.example .env
# .env 편집
ELEVENLABS_API_KEY=...   # 필수: TTS + Scribe
OPENAI_API_KEY=...       # 선택: 대본 생성(없으면 원문 추출), photo 모드는 필수
```

`.env`는 git에 올리지 않는다(`.gitignore`).

## 3. 실행

```bash
uv run md2short run samples/briefing.md            # 일반 마크다운
uv run md2short run samples/storyboard.md          # ### N컷 스토리보드
uv run md2short run my.md --visual-mode photo -o output/photo.mp4
uv run md2short status <job_id>                    # 상태·QC·비용
uv run md2short clean --older-than 7d --dry-run    # 오래된 job 정리
uv run md2short --help
```

주요 옵션: `--speed 0.7~1.2`, `--bg '#FFFFFF'`, `--chunk-size 1~24`, `--model gpt-5-mini`,
`--no-opening`, `--outro`, `--no-endcard`(투자 면책 엔드카드 생략), `--output ''`(사본 비활성화). 전체 명세는 `docs/architecture.md` §6.

종료 코드: `0` qc_passed, `1` 입력 오류(인자·키 누락), `2` 실행 중 예외 또는 qc_failed.

산출물은 모두 `jobs/<job_id>/` 아래에 남는다(`status.json`, `qc_report.json`, `logs/`,
`transcripts/words.json`, `edit/edl.json`, `edit/props.json`, `edit/final.mp4`). 최종본 사본은 `output/ret.mp4`.

### 브랜드 자산(선택)

| 경로 | 없을 때 |
| --- | --- |
| `img/header_logo.png` | 헤더에 텍스트 워드마크 "타이거살구브리핑" |
| `company/<회사명>.png` | 회사 로고 cue 생략 (있으면 발화 시점에 표시) |
| `fonts/SeoulNotice-Regular.woff2`, `fonts/SeoulAlrim-Bold.woff2` | Noto Sans KR 사용 |

## 4. 테스트

```bash
uv run ruff check .
uv run pytest -m "not render and not live"     # 외부 네트워크 없이 도는 기본 스위트
pnpm -C remotion exec tsc --noEmit             # Remotion 타입 검사
uv run pytest -m render                        # 실제 Remotion 렌더(ffmpeg + 브라우저 + tests/fixtures/probe 필요)
uv run pytest -m live                          # 실제 ElevenLabs 호출(.env 필요, 과금) → tests/fixtures/probe 생성
```

Python 계약(`md2short/schema.py`)을 바꾸면 TS 타입을 다시 만든다: `scripts/gen_types.sh`.
