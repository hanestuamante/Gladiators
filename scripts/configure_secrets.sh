#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${repo_root}/.env"

printf 'Nhập HF_TOKEN (nội dung sẽ không hiển thị): '
IFS= read -r -s api_key
printf '\n'

if [[ -z "${api_key}" ]]; then
  printf 'Không ghi file: key rỗng.\n' >&2
  exit 1
fi

printf 'HF model ID hoặc Inference Endpoint URL [Qwen/Qwen3-32B]: '
IFS= read -r hf_model
hf_model="${hf_model:-Qwen/Qwen3-32B}"
printf 'Inference provider [auto]: '
IFS= read -r hf_provider
hf_provider="${hf_provider:-auto}"

umask 077
temp_file="$(mktemp "${repo_root}/.env.XXXXXX")"
if [[ -f "${env_file}" ]]; then
  awk '!/^(HF_TOKEN|HF_MODEL|HF_INFERENCE_PROVIDER)=/' "${env_file}" > "${temp_file}"
fi
printf 'HF_TOKEN=%s\n' "${api_key}" >> "${temp_file}"
printf 'HF_MODEL=%s\n' "${hf_model}" >> "${temp_file}"
printf 'HF_INFERENCE_PROVIDER=%s\n' "${hf_provider}" >> "${temp_file}"
mv "${temp_file}" "${env_file}"
chmod 600 "${env_file}"
unset api_key hf_model hf_provider

printf 'Đã lưu HF_TOKEN vào %s với quyền 600. File này đã được gitignore.\n' "${env_file}"
