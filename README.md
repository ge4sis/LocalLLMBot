# Local LLM Telegram Bridge (Advanced)

Mac Studio (Apple Silicon) 환경에서 구동되는 로컬 LLM(예: LM Studio)을 텔레그램 봇으로 연결하는 브릿지 서버입니다. 외부망 접속 포트를 여는 대신 텔레그램의 Long Polling 방식을 사용하여 안전하게 로컬 모델 코어와 통신합니다.

최근 업데이트로 최신 **Zero-Dependency Python 3.9 MCP(Model Context Protocol) 클라이언트**가 탑재되어, LM Studio에 구성된 도구(Tools)들을 텔레그램 봇에서도 투명하게 사용할 수 있습니다.

## 주요 기능

1. **로컬 LLM 연동:** OpenAI 호환 API 인터페이스를 지원하는 LM Studio와 연동하여 텍스트 및 멀티모달(Vision) 질의응답을 지원합니다.
2. **동적 MCP(Model Context Protocol) 지원:** 
   * 파이썬 3.9 환경에서 돌아가는 경량화된 자체 JSON-RPC 클라이언트를 내장했습니다 (`mcp_client.py`).
   * 봇 구동 시 `~/.lmstudio/mcp.json` 설정을 자동으로 읽어 배경에서 MCP 서버들을 가동합니다.
   * `stdio` 기반(예: `yahoo-finance`, `fred` 등) 및 `http` POST 기반(예: `mcp.exa.ai`) MCP 서버와 완벽히 호환되며, 모델의 Function Calling(도구 사용)을 자동으로 중계합니다.
3. **추론 과정(Thinking Process) 필터링:** DeepSeek-R1, Qwen 모델 등에서 발생하는 `<think>...</think>` 블록 또는 `Thinking Process:` 로그를 정규식으로 필터링하여 사용자에게 깔끔한 최종 답변만 제공합니다.
4. **실시간 날짜 주입:** 매 세션마다 현재 시간 및 날짜를 시스템 프롬프트에 주입하여, 웹 검색 등의 도구 사용 시 모델이 최신 날짜를 기준으로 행동하도록 유도합니다.
5. **이미지(Vision) 처리:** 사진 전송 시 텔레그램 서버에서 이미지를 다운로드받고 Base64로 인코딩하여 LLM에 전송 분석합니다. 캡션이 없을 경우 자동 Fallback 메시지를 덧붙입니다.
6. **강력한 보안(Whitelist):** `.env` 파일에 지정된 `ALLOWED_USER_IDS` 목록의 유저 텔레그램 ID만 봇을 사용할 수 있습니다.

## 설치 및 실행 방법

### 1. 요구 사항
- Python 3.9 이상
- 로컬 실행 중인 LM Studio 서버 (CORS 및 로컬 API 서버 포트 활성화 됨)

### 2. 환경 설정
저장소를 클론한 뒤 가상 환경을 구축하고 패키지를 설치합니다.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. API 키 및 설정 세팅 (.env)
`.env.example` 파일을 복사하여 `.env` 파일을 생성하고 본인의 정보를 기입합니다.

```bash
cp .env.example .env
```

`.env` 파일 내용 예시:
```ini
# Telegram Bot API Token
TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"

# 쉼표로 구분된 접근 허용 텔레그램 User ID 목록
ALLOWED_USER_IDS="12345678,87654321"

# LM Studio 포트 설정 (일반적으로 1234)
LM_STUDIO_BASE_URL="http://127.0.0.1:1234/v1"
LM_STUDIO_API_KEY="sk-lm-api-key"
```

### 4. 실행
```bash
python bot.py
```

## 시스템 구조

*   `bot.py`: 텔레그램 메시지 폴링, 화이트리스트 검사, 텍스트/이미지 이벤트 처리, 세션 초기화 및 타임스탬프 주입.
*   `llm.py`: AsyncOpenAI 클라이언트 래퍼로, `<think>` 블록 제거, 메시지 히스토리 관리 및 MCP 도구 호출 루프(Tool execution proxy)를 담당합니다.
*   `mcp_client.py`: Zero-dependency 커스텀 MCP 클라이언트로, LM Studio의 `mcp.json` 파일을 파싱하여 도구 스키마를 변환 추출하고 실제 서버와의 입출력을 중계합니다.
*   `config.py`: `.env` 파일의 환경변수를 불러와 애플리케이션 전반에 설정값을 공급합니다.

## 주의 사항
- `mcp.json` 파일은 `mcp_client.py`에서 기본적으로 `~/.lmstudio/mcp.json` 경로를 탐색합니다. 다른 위치에 있다면 경로를 수정하시기 바랍니다.
- 텔레그램의 긴 응답 제한(4096자)을 우회하기 위해 `send_long_message` 헬퍼 함수가 구현되어 있어 텍스트를 청크로 나누어 순차적으로 보냅니다.
- 봇의 모든 통신은 외부 텔레그램 서버로 송신(Outbound loop)될 뿐 내부 포트를 직접 인바운드 개방하지 않아 안전합니다.
