#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${1:-}"
if [[ -z "${BACKEND_URL}" ]]; then
    echo "Usage: $0 <https://your-machine.your-tailnet.ts.net>" >&2
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "[ERROR] curl command not found." >&2
    exit 1
fi

REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-15}"
CHECK_ORIGIN_HEADER="${CHECK_ORIGIN_HEADER:-}"
VERBOSE_BODY="${VERBOSE_BODY:-0}"

HEALTH_URL="${BACKEND_URL%/}/health"
RUNTIME_URL="${BACKEND_URL%/}/api/codex/runtime/info"
SESSIONS_URL="${BACKEND_URL%/}/api/codex/sessions"
STREAMS_URL="${BACKEND_URL%/}/api/codex/streams"
FILES_LIST_URL="${BACKEND_URL%/}/api/codex/files/list"
GIT_SYNC_URL="${BACKEND_URL%/}/api/codex/git/sync?repo_target=codex_agent"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

LAST_STATUS_CODE=''
LAST_BODY=''

request_json() {
    local method="$1"
    local url="$2"
    local body_file="${TMP_DIR}/body.json"
    local body_payload="${3:-}"
    local status_code=''

    if [[ -n "${body_payload}" ]]; then
        status_code="$(
            curl --silent --show-error --max-time "${REQUEST_TIMEOUT_SECONDS}" \
                --output "${body_file}" --write-out '%{http_code}' \
                -X "${method}" \
                -H 'Content-Type: application/json' \
                --data "${body_payload}" \
                "${url}"
        )"
    else
        status_code="$(
            curl --silent --show-error --max-time "${REQUEST_TIMEOUT_SECONDS}" \
                --output "${body_file}" --write-out '%{http_code}' \
                -X "${method}" \
                "${url}"
        )"
    fi
    LAST_STATUS_CODE="${status_code}"
    LAST_BODY="$(cat "${body_file}")"
}

assert_http_2xx() {
    local step_label="$1"
    local request_url="$2"
    local status_group="${LAST_STATUS_CODE:0:1}"
    if [[ "${status_group}" != "2" ]]; then
        echo "[ERROR] ${step_label} failed (${request_url})" >&2
        echo "[ERROR] HTTP ${LAST_STATUS_CODE}" >&2
        echo "[ERROR] Body: ${LAST_BODY}" >&2
        if [[ "${LAST_STATUS_CODE}" == "401" ]] && echo "${LAST_BODY}" | grep -q 'Unauthorized'; then
            echo "[HINT] 현재 URL이 Codex 백엔드가 아닌 다른 서비스(401)를 가리키고 있을 가능성이 큽니다." >&2
            if command -v tailscale >/dev/null 2>&1; then
                echo "[HINT] tailscale serve status를 확인하세요:" >&2
                tailscale serve status >&2 || true
            fi
        fi
        exit 1
    fi
}

extract_session_id() {
    echo "${LAST_BODY}" | tr -d '\n' | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]\+\)".*/\1/p' | head -n 1
}

print_body_if_verbose() {
    if [[ "${VERBOSE_BODY}" == "1" ]]; then
        echo "${LAST_BODY}"
    fi
}

extract_bool_field() {
    local key_name="$1"
    echo "${LAST_BODY}" | tr -d '\n' | sed -n "s/.*\"${key_name}\"[[:space:]]*:[[:space:]]*\\(true\\|false\\).*/\\1/p" | head -n 1
}

echo "[INFO] Checking ${HEALTH_URL}"
request_json GET "${HEALTH_URL}"
assert_http_2xx "health check" "${HEALTH_URL}"
print_body_if_verbose

echo "[INFO] Checking ${RUNTIME_URL}"
request_json GET "${RUNTIME_URL}"
assert_http_2xx "runtime info" "${RUNTIME_URL}"
print_body_if_verbose
FILES_API_ENABLED="$(extract_bool_field files_api_enabled)"
GIT_API_ENABLED="$(extract_bool_field git_api_enabled)"
echo "[INFO] Runtime flags: files_api_enabled=${FILES_API_ENABLED:-unknown}, git_api_enabled=${GIT_API_ENABLED:-unknown}"

echo "[INFO] Checking ${SESSIONS_URL} (list)"
request_json GET "${SESSIONS_URL}"
assert_http_2xx "sessions list" "${SESSIONS_URL}"
SESSION_COUNT="$(echo "${LAST_BODY}" | tr -d '\n' | sed -n 's/.*"session_count"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n 1)"
echo "[INFO] sessions list ok (session_count=${SESSION_COUNT:-unknown})"
print_body_if_verbose

RUN_LABEL="$(date +%Y%m%d-%H%M%S)"
SESSION_TITLE="tailscale-smoke-${RUN_LABEL}"
CREATE_PAYLOAD="{\"title\":\"${SESSION_TITLE}\"}"

echo "[INFO] Checking ${SESSIONS_URL} (create)"
request_json POST "${SESSIONS_URL}" "${CREATE_PAYLOAD}"
assert_http_2xx "session create" "${SESSIONS_URL}"
print_body_if_verbose
SESSION_ID="$(extract_session_id)"
if [[ -z "${SESSION_ID}" ]]; then
    echo "[ERROR] session create 응답에서 session_id를 파싱하지 못했습니다." >&2
    exit 1
fi

echo "[INFO] Checking ${SESSIONS_URL}/${SESSION_ID} (detail)"
request_json GET "${SESSIONS_URL}/${SESSION_ID}"
assert_http_2xx "session detail" "${SESSIONS_URL}/${SESSION_ID}"
print_body_if_verbose

echo "[INFO] Checking ${SESSIONS_URL}/${SESSION_ID} (delete)"
request_json DELETE "${SESSIONS_URL}/${SESSION_ID}"
assert_http_2xx "session delete" "${SESSIONS_URL}/${SESSION_ID}"
print_body_if_verbose

echo "[INFO] Checking ${STREAMS_URL} (list)"
request_json GET "${STREAMS_URL}"
assert_http_2xx "stream list" "${STREAMS_URL}"
STREAM_COUNT="$(echo "${LAST_BODY}" | tr -d '\n' | sed -n 's/.*"streams"[[:space:]]*:[[:space:]]*\[\(.*\)\].*/\1/p' | awk 'length{print 1; next} {print 0}' | head -n 1)"
if [[ "${STREAM_COUNT}" == "1" ]]; then
    echo "[INFO] stream list ok (non-empty)"
else
    echo "[INFO] stream list ok (empty)"
fi
print_body_if_verbose

if [[ "${FILES_API_ENABLED}" == "false" ]]; then
    echo "[INFO] Checking ${FILES_LIST_URL} disabled behavior (expected 403)"
    request_json POST "${FILES_LIST_URL}" '{}'
    if [[ "${LAST_STATUS_CODE}" != "403" ]]; then
        echo "[ERROR] files/list expected 403 but got HTTP ${LAST_STATUS_CODE}" >&2
        echo "[ERROR] Body: ${LAST_BODY}" >&2
        exit 1
    fi
fi

if [[ "${GIT_API_ENABLED}" == "false" ]]; then
    echo "[INFO] Checking ${GIT_SYNC_URL} disabled behavior (expected 403)"
    request_json GET "${GIT_SYNC_URL}"
    if [[ "${LAST_STATUS_CODE}" != "403" ]]; then
        echo "[ERROR] git/sync expected 403 but got HTTP ${LAST_STATUS_CODE}" >&2
        echo "[ERROR] Body: ${LAST_BODY}" >&2
        exit 1
    fi
fi

if [[ -n "${CHECK_ORIGIN_HEADER}" ]]; then
    echo "[INFO] Checking CORS header for Origin: ${CHECK_ORIGIN_HEADER}"
    CORS_HEADERS="$(
        curl --silent --show-error --max-time "${REQUEST_TIMEOUT_SECONDS}" \
            --output /dev/null --dump-header - \
            -H "Origin: ${CHECK_ORIGIN_HEADER}" \
            "${HEALTH_URL}"
    )"
    echo "${CORS_HEADERS}" | grep -i '^Access-Control-Allow-Origin:' || true
fi

echo "[INFO] Tailscale backend smoke checks passed"
