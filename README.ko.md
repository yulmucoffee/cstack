# cstack

[![ci](https://github.com/yulmucoffee/cstack/actions/workflows/ci.yml/badge.svg)](https://github.com/yulmucoffee/cstack/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[English](README.md) · **한국어**

**머지 전에 증거부터.** Claude Code, Codex, Cursor에 "PR 리뷰해줘", "코드 검토해줘"라고만 해도 cstack의 리뷰 절차가 돌아갑니다. cstack은 **Claude Code, Codex, Cursor**에서 함께 쓰는 에이전트 스킬 하나, **Cursor BugBot**용 리뷰 규칙 파일, 작은 **GitHub 머지 게이트**로 이뤄져 있습니다. Claude Code 팀의 계층형 코드 리뷰 프로세스와 poteto의 [pstack](https://github.com/cursor/plugins/tree/main/pstack) 엔지니어링 원칙을 여러분의 레포에 그대로 가져옵니다.

목표는 코드나 리뷰 코멘트를 늘리는 것이 아닙니다. 가장 작은 올바른 변경을 실제 화면과 실제 실행으로 증명하고, 새 컨텍스트에서 리뷰하고, 사람의 주의는 위험한 곳에만 쓰는 것입니다.

## 왜 만들었나

이제 에이전트는 사람이 다 읽을 수 없을 만큼 빠르게 PR을 만듭니다. Claude Code 팀은 이 문제를 [이렇게 풀었다고](https://claude.dev/blog/solving-code-review-at-anthropic/) 밝혔습니다. 머지된 PR은 두 배 넘게 늘었는데 되돌린 PR의 비율은 40% 넘게 줄었습니다. 리뷰를 없앤 것이 아닙니다. 읽는 일의 대부분을 기계에 넘기고, 검사를 여러 겹으로 쌓고, 사람 승인을 위험도에 맞추고, 리뷰가 끝없이 돌지 않고 수렴하도록 만들었습니다.

pstack은 나머지 절반을 다룹니다. 에이전트가 신뢰받을 만한 결과를 내려면 어떻게 일해야 하는가입니다. 작업을 날카롭게 정의하고, 데이터 형태를 먼저 정하고, 증상이 아니라 근본 원인을 고치고, 변경이 안전한 단 하나의 근거를 실행해서 증명하고, 여러 모델로 적대적 리뷰를 합니다.

cstack은 이 둘을 설치하고 읽을 수 있는 파일로 묶었습니다. 따로 띄울 서비스는 없습니다.

## 구성

| 계층 | 파일 | 읽는 쪽 | 강제력 |
| --- | --- | --- | --- |
| 스킬 | `skills/cstack/SKILL.md`와 `references/` | Claude Code, Codex, Cursor 에이전트 | 없음. 에이전트의 작업 방식을 정합니다. |
| BugBot 규칙 | `.cursor/BUGBOT.md`, `.cursor/config/bugbot.yaml` | 모든 PR의 Cursor BugBot | 없음. BugBot이 무엇을 보고할지 정합니다. |
| 리뷰 라우팅 | `CLAUDE.md`, `AGENTS.md`의 마커 블록 | Claude Code, Codex, Cursor | 없음. 모든 리뷰 요청을 스킬로 보냅니다. |
| 리뷰 규칙 | `REVIEW.md` (시작용 템플릿) | 모든 AI 리뷰어와 팀 | 없음. 코드 오너가 다듬습니다. |
| 머지 게이트 | `.cstack/gate.py`, `.cstack/policy.json`, `.github/workflows/cstack-gate.yml` | GitHub Actions | **있음.** 룰셋에서 `cstack-risk-gate`를 필수로 지정하면 동작합니다. |

변경 하나가 지나가는 길입니다.

```
작성자 검증 → 새 컨텍스트 리뷰 → 보안 리뷰 → 필수 CI
→ 위험도별 사람 승인 (cstack-risk-gate) → 머지 큐 → 플래그 / 단계적 배포 → 롤백
```

계층마다 잡는 문제와 놓치는 문제가 있습니다. 모든 계층을 통과하는 문제는 드물고, 남은 것은 롤백이 처리합니다.

## 설치

Python 3.10 이상만 있으면 됩니다. 설치 스크립트는 네트워크를 쓰지 않습니다.

### 개인용: 스킬만

레포를 건드리지 않고, 여는 모든 레포에서 cstack을 씁니다.

```bash
git clone https://github.com/yulmucoffee/cstack.git
```

```bash
python3 cstack/scripts/install.py --global
```

`~/.claude/skills/cstack/` (Claude Code)과 `~/.agents/skills/cstack/` (Codex)에 설치합니다. 설치된 도구에 한해 `~/.claude/CLAUDE.md`와 `~/.codex/AGENTS.md`에 리뷰 라우팅 블록을 넣습니다. 업그레이드 추적용으로 `~/.cstack/manifest.json`도 만듭니다. Cursor는 두 스킬 폴더를 모두 읽습니다. 업그레이드하려면 `git pull` 후 같은 명령을 다시 실행하세요.

**Claude Code 플러그인.** Claude Code 안에서 플러그인으로 설치할 수도 있습니다.

```text
/plugin marketplace add yulmucoffee/cstack
/plugin install cstack@cstack
```

Claude Code 2.1.275 이상에서는 `/plugin install cstack --marketplace yulmucoffee/cstack` 한 줄로 끝납니다. 플러그인 스킬은 네임스페이스가 붙어서 `/cstack:cstack`으로 호출합니다. 플러그인은 `CLAUDE.md`를 수정할 수 없으니, [모든 리뷰를 cstack으로](#모든-리뷰를-cstack으로)의 라우팅 문구를 직접 넣어 주세요.

### 프로젝트용: 스킬, BugBot, 게이트

cstack 체크아웃에서 실행하고 대상 레포를 지정합니다. 먼저 dry run으로 무엇이 바뀌는지 확인하세요.

```bash
python3 scripts/install.py --target /path/to/your-repo --dry-run
```

```bash
python3 scripts/install.py --target /path/to/your-repo
```

| 대상 레포의 경로 | 종류 | 다시 설치할 때 |
| --- | --- | --- |
| `.claude/skills/cstack/`, `.agents/skills/cstack/` | 관리 파일 | 직접 수정하지 않았으면 업그레이드 |
| `.cursor/BUGBOT.md` | 마커 블록 | `<!-- cstack:begin -->` 블록만 교체 |
| `.cstack/gate.py`, `.github/workflows/cstack-gate.yml` | 관리 파일 | 직접 수정하지 않았으면 업그레이드 |
| `.cstack/policy.json`, `.cursor/config/bugbot.yaml`, `REVIEW.md`, `.github/pull_request_template.md` | 시드 파일 | 한 번만 만들고 절대 덮어쓰지 않음 |
| `CLAUDE.md`, `AGENTS.md` | 마커 블록 | 리뷰 라우팅 블록만 추가하거나 교체하고, 나머지 내용은 그대로 둠 |
| `.cstack/manifest.json` | 기록용 | 관리 파일의 해시 |

옵션은 이렇습니다. `--no-gate`를 주면 게이트 워크플로, `gate.py`, `policy.json`을 건너뛰고, 스킬, BugBot 파일, `REVIEW.md`, PR 템플릿은 그대로 설치합니다. `--hosts claude`, `--hosts codex`, `--hosts claude,codex,cursor`로 스킬 위치를 고릅니다. `--no-routing`을 주면 `CLAUDE.md`와 `AGENTS.md`를 건드리지 않습니다. `@AGENTS.md`만 불러오는 `CLAUDE.md`는 수정하지 않습니다. `AGENTS.md`의 블록이 이미 Claude Code에 전달되기 때문입니다. `--force`는 직접 수정한 관리 파일을 덮어씁니다. 시드 파일은 `--force`로도 덮어쓰지 않습니다. GitHub가 찾는 위치 어디든 PR 템플릿이 이미 있으면 그대로 둡니다.

결과를 커밋하고, 에이전트를 재시작하거나 새 세션을 열어 스킬을 불러오세요. 나중에 업그레이드할 때는 cstack 체크아웃에서 `git pull` 후 같은 명령을 실행합니다. 시드 파일은 여러분 소유라 갱신되지 않으니, 새 키가 생겼는지 `configs/policy.json`과 비교하세요. 필수 체크가 App에 묶여 있지 않으면 게이트가 경고를 출력합니다.

### 실제 운영 전에 꼭 할 일

GitHub에서 필수로 지정하기 전까지 게이트는 아무것도 막지 않습니다. 순서대로 진행하세요.

1. **신뢰 작성자 지정.** `.cstack/policy.json`의 `trusted_authors`에 신뢰하는 사람 메인테이너의 GitHub 로그인을 넣습니다. 기본값처럼 비어 있으면 모든 PR에 사람 승인 2개가 필요합니다. 민감 경로 목록을 확인하고, 필요하면 `additional_high_risk_patterns`에 추가합니다.
2. **BugBot 활성화.** Cursor 대시보드에서 해당 레포의 BugBot을 켭니다. YAML 파일은 설정만 할 뿐 BugBot을 켜지는 않습니다. BugBot이 꺼져 있으면 필수 체크인 `Cursor Bugbot`이 나타나지 않으므로 게이트는 계속 막힙니다. 의도된 동작입니다. 다른 AI 리뷰어를 쓴다면 `required_check_names`와 `required_check_apps`를 바꾸세요.
3. **필수 체크 지정.** 기본 브랜치 룰셋에서 `cstack-risk-gate`, 빌드와 테스트, 보안 스캔, `Cursor Bugbot`을 필수로 지정합니다. 각 체크를 발행하는 GitHub App에 묶어 두세요. 필수 리뷰, 새 커밋 시 기존 승인 무효화(dismiss stale approvals), 대화 해결 필수를 켜고, 우회할 수 있는 사람을 제한합니다.
4. **게이트 자체를 보호.** `pull_request` 이벤트에서 GitHub는 PR 쪽 워크플로 파일을 실행합니다. 그래서 PR이 `cstack-gate.yml`을 고칠 수 있습니다. 요금제에서 지원하면 룰셋 규칙 *Require workflows to pass before merging*으로 기본 브랜치의 워크플로를 지정하세요. 지원하지 않으면 `.github/workflows/`, `.cstack/`, `.cursor/`, `CODEOWNERS`에 CODEOWNERS를 걸고 코드 오너 리뷰를 필수로 합니다. 게이트는 이 경로들을 이미 고위험으로 분류합니다.
5. **버려도 되는 PR로 시험.** 문서 변경, 코드 변경, 워크플로 변경을 하나씩 올려 보고 나서 사람 없는 머지를 허용하세요.

cstack은 스스로 머지하지 않습니다. 게이트 통과는 "머지해도 된다"는 뜻이지 "머지하라"는 뜻이 아닙니다.

## 사용법

### 모든 리뷰를 cstack으로

스킬 이름을 부를 필요가 없습니다. "이 PR 리뷰해줘", "내 변경사항 검토해줘", "머지해도 돼?", "review PR 42" 같은 요청은 모두 cstack의 리뷰 절차로 들어갑니다.
1. 대상을 정합니다. PR 번호, 브랜치, 커밋하지 않은 변경 중 하나입니다.
2. 읽기 전용으로 진행합니다.
3. 독립 리뷰어 여럿에게 나눠 맡기고, 발견 사항을 하나씩 검증합니다.
4. 안전의 단 하나의 근거를 증명합니다.
5. 요청한 언어로 보고합니다.

`/code-review`, `/security-review` 같은 내장 명령도 그대로 쓰이는데, cstack 안의 리뷰어 중 하나로 돌아갑니다.

안정적으로 동작하게 하는 장치는 두 가지입니다. 스킬 설명이 리뷰 요청을 먼저 가져가도록 쓰여 있습니다. 그리고 설치 스크립트가 에이전트가 세션마다 처음 읽는 `CLAUDE.md`와 `AGENTS.md`에 아래 블록을 넣습니다.

```markdown
## Code review (cstack)

For any request to review code, a diff, a branch, a commit or a pull request, in any wording or language ("review this PR", "code review", "check my changes", "PR 리뷰", "코드 검토"), use the `cstack` skill in `review` mode, even when another review skill or command also matches. Built-in review commands such as `/code-review`, `/security-review` or `/review` run as reviewers inside cstack, not instead of it. Requests to babysit, merge or ship a PR also go through cstack.
```

Claude Code 플러그인으로 설치했거나 Cursor 전체 프로젝트에 적용하려면, 같은 문구를 `~/.claude/CLAUDE.md` 또는 Cursor의 **Settings → Rules → User Rules**에 붙여 넣으세요.

### 직접 호출하기

| 호스트 | 호출 |
| --- | --- |
| Claude Code | `/cstack` (프로젝트 또는 개인 설치), `/cstack:cstack` (플러그인). 작업이 맞으면 Claude가 알아서 불러오기도 합니다. |
| Codex | `$cstack`, 또는 `/skills`에서 선택합니다. 작업이 맞으면 알아서 불러오기도 합니다. |
| Cursor | Agent 채팅에서 `/cstack`을 입력하거나 에이전트가 고르게 둡니다. |
| BugBot | 할 일 없음. 모든 PR에서 `.cursor/BUGBOT.md`를 읽습니다. |

스킬은 요청을 보고 모드를 고른 뒤, 어떤 모드인지 첫 줄에 밝힙니다.

| 모드 | 요청 예 | 코드 수정 | 멈추는 지점 |
| --- | --- | --- | --- |
| `build` | 기능 추가, 변경 | 예 | 증거와 함께 PR 생성 |
| `fix` | 버그 수정 | 예 | 실패 후 통과하는 증거, PR 생성 |
| `review` | 리뷰, "확실해?" | 아니요 | 발견 사항과 판정 |
| `investigate` | 동작 원리나 이유 질문 | 아니요 | 근거를 단 답변 |
| `babysit` | "PR 42 초록불 만들어줘", "BugBot 코멘트 처리해줘", "PR 42 상태 봐줘" | PR 브랜치에서만 수정 | `MERGE-READY` 또는 `BLOCKED` |
| `ship` | "ship", "머지", "랜딩"을 명시적으로 요청 | 머지 | 검증된 구간의 맨 위 |

### 프롬프트 예시

```text
/cstack 이 브랜치를 PR 설명과 대조해서 리뷰해줘. 가장 위험한 가정은 실제 코드를 실행하는 스크립트로 증명해. 파일은 고치지 마.
```

```text
/cstack 느린 네트워크에서 내보내기 버튼이 두 번 제출돼. 먼저 실제 페이지에서 재현하고, 고친 다음 전후를 보여줘.
```

```text
/cstack PR 42를 merge-ready까지 봐줘. BugBot 스레드를 분류하고 뭐가 막고 있는지 알려줘. 머지는 하지 마.
```

```text
/cstack PR 41부터 43까지 아래에서부터 ship해. 독립 검증 판정이 없는 첫 PR에서 멈춰.
```

```text
$cstack 현재 브랜치를 살펴보고 실패 경로를 확인해서 머지 가능 여부를 판정해줘. 머지하지 마.
```

### 좋은 프롬프트 쓰는 법

pstack의 프롬프팅 조언을 따릅니다. 목표와 "끝났다"를 판단할 기준을 말하고, 단계는 스킬에 맡기세요.

- **넣을 것:** 목표, 통과와 실패가 갈리는 완료 기준, 보고 싶은 증거(명령 출력, 스크린샷, 전후 수치), 이미 아는 것(재현 단계, 로그), 실제 제약("재현부터", "동작 변경 없이", "머지하지 마").
- **뺄 것:** 구현 방법, 단계 목록, 원인에 대한 내 추측. 추측을 말하면 탐색 범위가 좁아집니다.
- **한 줄로 방향 잡기:** "재현해 달라고 했지, 아직 고치라고 하지 않았어." "빌드 로그 말고 실제 출력을 보여줘."

### 보고 형식

```text
MODE: review | VERDICT: PASS+NOTES | REF: 9f2c1e4
FINDINGS: 1 actionable
  [ACT ON][high] src/cache/evict.ts:L88 trigger: refresh during eviction -> live entry dropped -> repro: scripts/evict-race.ts (fails on 9f2c1e4)
PROOF: npm test -- cache -> 42 passed; node scripts/evict-race.ts -> FAIL as expected
SAFETY FACT: eviction only removes entries past TTL: UNPROVEN (race above breaks it)
RISK: tier medium, approvals 0/1, Cursor Bugbot success
INDEPENDENCE: Claude Opus subagent + Sonnet subagent (different models)
NEXT: guard eviction with the entry's generation counter and rerun the race script
```

## 위험 등급

게이트는 바뀐 경로와 작성자로 최소 기준을 계산합니다. 사람과 리뷰어는 언제든 등급을 올릴 수 있습니다.

| 변경 | 신뢰 작성자 | 그 외 |
| --- | ---: | ---: |
| 문서만 (`.md`, `.mdx`, `.rst`, `.adoc`, `docs/` 아래 이미지) | 0 | 2 |
| 코드, 설정, 의존성 매니페스트, 에이전트·리뷰어 지침 (`CLAUDE.md`, `AGENTS.md`, `REVIEW.md`, 스킬) | 1 | 2 |
| CI 워크플로와 그 밖의 CI 설정, CODEOWNERS, `.cstack/`, BugBot 설정, 에이전트 훅과 MCP 설정, auth, security, billing, payments, migrations, secrets, Terraform, lockfile | 2 | 2 |

모든 등급에서 게이트는 다음도 요구합니다. 승인은 현재 head 커밋에 대한 것이어야 하고, 작성자가 아닌 레포 owner, member, collaborator의 사람 계정이어야 합니다. 권한 없는 계정의 승인은 세지 않습니다. 남아 있는 변경 요청과 미해결 리뷰 스레드가 없어야 합니다. 필수 체크는 지정된 App이 발행한 `success`여야 하고, `neutral`은 통과가 아닙니다. 사람 없는 머지는 자동 리뷰 체크가 하나 이상 필수일 때만 허용합니다. API 오류, draft PR, 잘못된 정책 파일은 모두 차단으로 처리합니다.

블로그의 등급보다 일부러 더 엄격하게 잡았습니다. 근거가 쌓이면 완화하세요. 규칙 전체와 한계는 [설계와 신뢰 경계](docs/design.md)에 있습니다.

### `policy.json`

| 키 | 기본값 | 의미 |
| --- | --- | --- |
| `trusted_authors` | `[]` | 가벼운 등급을 받는 GitHub 로그인. 대소문자 구분 없음. |
| `additional_high_risk_patterns` | `infra/**`, `**/deploy/**`, `**/production/**` | 항상 사람 2명이 필요한 추가 경로. |
| `required_check_names` | `["Cursor Bugbot"]` | head에서 `success`여야 하는 체크. |
| `required_check_apps` | `{"Cursor Bugbot": "cursor"}` | 이 GitHub App이 발행한 체크만 인정. |
| `approver_associations` | `OWNER`, `MEMBER`, `COLLABORATOR` | 승인으로 인정할 관계. 조직 멤버 모두가 승인하면 안 되는 경우 좁히세요. |
| `require_resolved_review_threads` | `true` | 미해결 리뷰 스레드가 있으면 차단. |
| `check_wait_seconds` | `600` | 아직 실행 중인 필수 체크를 기다리는 시간. 워크플로의 `timeout-minutes`보다 짧게 유지하세요. |

## 스킬이 다르게 하는 것

- **주장이 아니라 증거.** 모든 주장에 증거를 붙이거나 `measured`, `inferred`, `guess` 중 하나로 표시합니다. 돌리지 않은 테스트를 돌렸다고 하지 않습니다.
- **새 컨텍스트의 독립 리뷰.** 읽기 전용 리뷰어 둘 이상을 병렬로, 가능하면 서로 다른 모델로 돌립니다. 리뷰어에게는 의도, diff, 루브릭만 줍니다. 실제로 확보한 독립성을 그대로 밝힙니다.
- **게시 전 검증.** 발견 사항마다 별도 패스로 확인합니다. 스타일 지적은 버리고, 기존 버그는 작성자 탓으로 보이지 않게 pre-existing으로 표시합니다.
- **안전의 단 하나의 근거.** 변경이 안전한 단 하나의 사실을 찾아서 증거 사다리를 따라 끝까지 증명합니다. "주장"에서 시작해 "실행 중인 앱에서 재현"까지 갑니다. 증명하지 못하면 `UNPROVEN`이라고 씁니다.
- **수렴.** 같은 문제로 세 번 돌면 접근을 다시 생각합니다. 첫 패스 이후에는 새 diff만 리뷰하고, 버그 유형을 짚고, 같은 지적을 반복하지 않습니다.
- **회의적인 BugBot 분류.** 스레드마다 `fix`, 반증을 단 `dismiss`, `ask` 중 하나로 분류합니다. 보안, 데이터, 마이그레이션 관련 지적은 절대 자동으로 넘기지 않습니다.
- **babysit은 ship이 아니다.** babysit은 merge-ready에서 멈춥니다. ship은 명시적 요청과 PR별 독립 검증 판정이 필요하고, 스택 맨 아래부터 끊김 없이 검증된 구간만 머지합니다.
- **교훈은 구조로.** 반복되는 지적은 린트 규칙, 테스트, `REVIEW.md` 한 줄이 됩니다. 장애는 평가(eval) 케이스가 됩니다.

## 레포 구조

```text
skills/cstack/SKILL.md                     모든 에이전트 호스트용 워크플로
skills/cstack/agents/openai.yaml           Codex 표시 메타데이터
skills/cstack/references/                  리뷰 루브릭, 머지 플레이북, BugBot 분류, 원칙, eval
.claude-plugin/                            Claude Code 플러그인·마켓플레이스 매니페스트
.cursor/BUGBOT.md                          BugBot 리뷰 규칙 (이 레포에도 적용)
.cursor/config/bugbot.yaml                 BugBot 레포 설정
templates/workflows/cstack-gate.yml        대상 레포에 설치되는 게이트 워크플로
templates/REVIEW.md                        시작용 REVIEW.md
templates/routing.md                       CLAUDE.md, AGENTS.md용 리뷰 라우팅 블록
.github/PULL_REQUEST_TEMPLATE.md           PR 템플릿: Why, Scope, Testing, Risk, How to revert
configs/policy.json                        기본 게이트 정책
scripts/gate.py                            게이트 (표준 라이브러리만 사용)
scripts/install.py                         설치 스크립트 (표준 라이브러리만 사용)
tests/                                     게이트와 설치 스크립트 테스트
docs/design.md                             신뢰 경계와 알려진 한계
```

## 개발

```bash
python3 -m unittest discover -s tests -v
```

아무것도 쓰지 않고 실제 PR에 게이트를 돌려 보려면 이렇게 합니다.

```bash
GH_TOKEN="$(gh auth token)" GITHUB_REPOSITORY=owner/repo PR_NUMBER=123 CSTACK_CONFIG=configs/policy.json python3 scripts/gate.py
```

이슈와 PR 환영합니다. 스킬을 바꾸는 PR에는 그 변경이 에이전트 행동을 어떻게 바꾸는지, 가능하면 실제 작업에서의 전후 비교를 함께 적어 주세요.

## 출처

- Addy Osmani, Morgan Westlee Lunt, Qing Wang, [How the Claude Code team does code review](https://claude.dev/blog/solving-code-review-at-anthropic/) (2026년 10월 15일).
- Lauren Tan ([poteto](https://github.com/poteto)), [pstack](https://github.com/cursor/plugins/tree/main/pstack), MIT. 원칙, 리뷰 루브릭, BugBot 분류, 머지 규율을 가져와 다시 썼습니다. [NOTICE.md](NOTICE.md)를 참고하세요.

cstack은 독립 프로젝트이며 Anthropic, Cursor, OpenAI와 제휴하거나 보증받지 않았습니다.

## 라이선스

[MIT](LICENSE)
