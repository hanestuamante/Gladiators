#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${repo_root}/.env"
printf 'Nhập GROQ_API_KEY (nội dung sẽ không hiển thị): '
IFS= read -r -s api_key
printf '\n'
if [[ -z "${api_key}" ]]; then printf 'Không ghi file: key rỗng.\n' >&2; exit 1; fi
printf 'Groq model [openai/gpt-oss-20b]: '
IFS= read -r groq_model
groq_model="${groq_model:-openai/gpt-oss-20b}"

umask 077
temp_file="$(mktemp "${repo_root}/.env.XXXXXX")"
if [[ -f "${env_file}" ]]; then awk '!/^(GROQ_API_KEY|GROQ_MODEL|GLADIATORS_LLM_PROVIDER)=/' "${env_file}" > "${temp_file}"; fi
printf 'GROQ_API_KEY=%s\n' "${api_key}" >> "${temp_file}"
printf 'GROQ_MODEL=%s\n' "${groq_model}" >> "${temp_file}"
printf 'GLADIATORS_LLM_PROVIDER=groq\n' >> "${temp_file}"
mv "${temp_file}" "${env_file}"
chmod 600 "${env_file}"
unset api_key groq_model
printf 'Đã lưu Groq key/model và chọn provider=groq trong %s (quyền 600).\n' "${env_file}"
