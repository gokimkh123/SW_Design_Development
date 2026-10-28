#!/usr/bin/env sh
# 비밀 정보 커밋 차단 검사 (pre-commit hook · CI 공용)
# 사용: scripts/check-secrets.sh            → 추적 중인 전체 파일 검사 (CI)
#       scripts/check-secrets.sh --staged   → 커밋 대기 파일만 검사 (pre-commit)
# 검사 항목: .env 파일, 키 파일, API 키 · 토큰 · 개인키 문자열

SELF=scripts/check-secrets.sh
# 한글 등 비ASCII 경로를 따옴표 · 8진수 변환 없이 그대로 출력
GIT="git -c core.quotepath=off"
if [ "$1" = "--staged" ]; then
  files=$($GIT diff --cached --name-only --diff-filter=ACMR)
else
  files=$($GIT ls-files)
fi
[ -z "$files" ] && exit 0

fail=0

# 1) .env 파일 (.env.example 제외, *.env 포함)
bad=$(printf '%s\n' "$files" | grep -E '(^|/)\.env(\..+)?$|\.env$' | grep -vE '(^|/)\.env\.example$')
if [ -n "$bad" ]; then
  echo "[차단] .env 파일 커밋 금지:"; printf '%s\n' "$bad" | sed 's/^/  /'; fail=1
fi

# 2) 키 · 인증서 파일
bad=$(printf '%s\n' "$files" | grep -Ei '\.(pem|key|p12|pfx)$|(^|/)id_(rsa|ecdsa|ed25519)$|roommate_deploy')
if [ -n "$bad" ]; then
  echo "[차단] 키 파일 커밋 금지:"; printf '%s\n' "$bad" | sed 's/^/  /'; fail=1
fi

# 3) 비밀 문자열: Anthropic · OpenAI · GitHub · AWS 키, 개인키, 값이 채워진 *_API_KEY
PATTERN='sk-ant-[A-Za-z0-9_-]{16,}|sk-(proj-)?[A-Za-z0-9]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN ([A-Z]+ )?PRIVATE KEY-----|[A-Z_]*API_KEY[ ]*=[ ]*["'"'"']?[A-Za-z0-9_-]{16,}'
if [ "$1" = "--staged" ]; then
  hits=$(printf '%s\n' "$files" | grep -vxF "$SELF" | while IFS= read -r f; do
    $GIT diff --cached -U0 -- "$f" | grep -E '^\+' | grep -v '^+++' | grep -qE "$PATTERN" && echo "$f"
  done)
else
  hits=$($GIT grep -nE "$PATTERN" -- . ":(exclude)$SELF" | cut -d: -f1-2)
fi
if [ -n "$hits" ]; then
  echo "[차단] API 키 · 토큰 · 개인키로 보이는 문자열 발견:"
  # 값 노출 방지: 위치만 출력
  printf '%s\n' "$hits" | sed 's/^/  /'
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo ""
  echo "비밀 정보는 커밋하지 않는다. 키는 backend/.env(로컬) 또는 VM ~/roommate/.env에만 보관."
  echo "이미 키를 커밋 · push했다면 즉시 건한에게 알리고 키를 폐기(재발급)한다."
  exit 1
fi
echo "비밀 정보 검사 통과"
