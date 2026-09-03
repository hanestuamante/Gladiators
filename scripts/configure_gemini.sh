#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${repo_root}/.env"

printf 'Nhập GEMINI_API_KEY mới (nội dung sẽ không hiển thị): '
IFS= read -r -s api_key
printf '\n'
if [[ -z "${api_key}" ]]; then
  printf 'Không ghi file: key rỗng.\n' >&2
  exit 1
fi

umask 077
temp_file="$(mktemp "${repo_root}/.env.XXXXXX")"
if [[ -f "${env_file}" ]]; then
  awk '!/^(GEMINI_API_KEY|GLADIATORS_LLM_PROVIDER)=/' "${env_file}" > "${temp_file}"
fi
printf 'GEMINI_API_KEY=%s\n' "${api_key}" >> "${temp_file}"
printf 'GLADIATORS_LLM_PROVIDER=gemini\n' >> "${temp_file}"
mv "${temp_file}" "${env_file}"
chmod 600 "${env_file}"
unset api_key

printf 'Đã cập nhật Gemini key và chọn provider=gemini trong %s (quyền 600).\n' "${env_file}"
