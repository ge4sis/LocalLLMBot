# Spec.MD: Local LLM Telegram Bridge (Advanced)

## 1. Project Overview

* **Target:** Mac Studio M4 Max 기반 Local LLM(Qwen 2.5/3.5 Vision) 외부 연동.
* **Core Architecture:** * **Inbound:** Telegram Long Polling (No Tunneling, No Port Forwarding).
* **Inference:** LM Studio Local Server (OpenAI Compatible API).
* **Tooling:** LM Studio 내장 MCP(Model Context Protocol) 환경 그대로 활용.


## 2. System Architecture

| 구성 요소 | 기술 스택 | 비고 |
| --- | --- | --- |
| **Interface** | Telegram Bot API | 사용자 접점 (Mobile/Desktop) |
| **Bridge Server** | Python 3.9+ | 메시지 라우팅, 날짜 주입, 데이터 가공 (Polling 방식) |
| **LLM Engine** | LM Studio (Local) | Qwen 모델 로드 및 추론 전담 |
| **API Protocol** | OpenAI SDK | `base_url`을 로컬 서버로 지정 |
| **MCP Client** | Custom JSON-RPC | Python 3.9 호환 Zero-dependency. `mcp.json` 파싱 후 MCP 직접 연결 |


## 3. Functional Requirements

### 3.1 세션 및 컨텍스트 관리 (Session Management)

* **대화 유지:** `user_id`별로 대화 히스토리(List of Dicts)를 메모리에 상주시켜 문맥 유지.
* **세션 초기화:** `/new` 명령어를 수신하면 해당 유저의 대화 히스토리 초기화.
* **시스템 프롬프트:** 브릿지 서버 단계에서 기본 페르소나 또는 지시사항 주입 가능.

### 3.2 멀티모달 처리 (Vision Capability)

* **이미지 처리:** * 사용자가 사진 전송 시, 브릿지 서버가 텔레그램 서버에서 파일을 다운로드.
* 다운로드된 이미지를 **Base64**로 인코딩하여 LM Studio API의 `image_url` 필드에 매핑.

* **지시사항 매칭:** * 이미지와 텍스트가 함께 오면: 지시사항을 우선순위로 하여 모델에게 전달.
* 이미지만 오면: "오빠, 이 이미지로 뭘 도와줄까? 요약이나 분석 필요해?"라고 역질문(Fallback) 로직 수행.


### 3.3 MCP(Model Context Protocol) 동적 주입

* **로컬 MCP 파싱:** 브릿지 서버 내 커스텀 클라이언트(`mcp_client.py`)가 봇 시작 시 `~/.lmstudio/mcp.json`을 읽어 모든 설정된 도구 서버(Exa, Yahoo Finance 등)를 백그라운드에서 직접 구동(Subprocess)합니다.
* **표준화:** 가져온 JSON-RPC 도구 스키마들을 OpenAI의 `tools` 규격으로 변환하여 매 채팅 요청 시 모델에 동적으로 주입합니다.
* **명세 우회 해결:** 외부 API 접근 시 LM Studio의 자동 도구 주입이 제한되는 현상을 해결하기 위함이며, 모델이 도구를 호출(`tool_calls`)하면 브릿지가 로컬 MCP 프로세스의 응답을 받아 다시 대화 스트림에 반환하는 완벽한 Loop를 구성합니다.


## 4. Security & Access Control

### 4.1 민감 정보 및 설정 관리 (`.env` 활용)

*보안과 유연한 설정 관리를 위해 모든 토큰, ID, API 키 값들은 코드에 직접 하드코딩하지 않고 `.env` 파일로 분리하여 관리합니다.*

* **필수 관리 항목 (in `.env`):**
  * `TELEGRAM_BOT_TOKEN`: 텔레그램 봇 API 토큰.
  * `ALLOWED_USER_IDS`: 텔레그램 봇 접근을 허용할 유저 ID 목록.
  * `LM_STUDIO_BASE_URL`: 로컬 LM Studio API 주소 (기본값: http://127.0.0.1:1234/v1).
  * `LM_STUDIO_API_KEY`: LM Studio API 키.
* **보안 조치:** `.env` 파일은 `.gitignore`에 반드시 포함시켜 GitHub 등 외부에 노출되지 않도록 설정합니다. 협업 및 배포 환경 구성을 위해 템플릿 파일인 `.env.example`만 저장소에 커밋합니다.

### 4.2 화이트리스트(Whitelist) 시스템

* **등록 방식:** `.env`에 등록된 `ALLOWED_USER_IDS`를 애플리케이션 시작 시 리스트로 로드하여 관리.
* **검증 로직:** 1.  메시지 수신 시 가장 먼저 `update.effective_user.id` 체크.
2.  리스트에 없는 유저의 경우 **침묵 무시(Silent Ignore)** 또는 "권한이 없습니다" 통보 후 로그 기록.

### 4.2 네트워크 보안

* **Loopback 통신:** Python 브릿지와 LM Studio 간의 통신은 오직 `127.0.0.1` 내에서만 이루어짐.
* **Inbound 차단:** 모든 외부 통신은 내부에서 텔레그램으로 나가는 Outbound만 허용.


## 5. Exception Handling

* **모델 응답 지연:** M4 Max라도 Vision이나 복잡한 MCP 처리 시 시간이 걸릴 수 있으므로, 텔레그램의 "Typing..." 액션을 전송하여 연결 유지 알림.
* **API 에러:** LM Studio 서버 미가동 시 "현재 Mac Studio의 모델 서버가 꺼져 있어, 오빠."라고 명확히 에러 메시지 전송.


## 6. Implementation Checklist

* [ ] 텔레그램 `@BotFather`를 통한 API Token 발급.
* [ ] 본인 텔레그램 `user_id` 확인 및 설정.
* [ ] LM Studio API Server 활성화 (CORS 및 API 포트 확인).
* [ ] Python 환경 구축 (`python-telegram-bot`, `openai` 패키지 설치).