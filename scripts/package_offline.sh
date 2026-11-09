#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_NAME="text-ipa-zhuyin-presenter-offline"
OUT_DIR="${1:-${ROOT_DIR}/dist}"
STAGE_DIR="${OUT_DIR}/${PACKAGE_NAME}"

rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}"

cp -a "${ROOT_DIR}/app" "${STAGE_DIR}/app"
cp -a "${ROOT_DIR}/backend" "${STAGE_DIR}/backend"
cp -a "${ROOT_DIR}/data" "${STAGE_DIR}/data"
cp -a "${ROOT_DIR}/docs" "${STAGE_DIR}/docs"
cp -a "${ROOT_DIR}/samples" "${STAGE_DIR}/samples"
cp -a "${ROOT_DIR}/tests" "${STAGE_DIR}/tests"
cp "${ROOT_DIR}/README.md" "${STAGE_DIR}/README.md"
cp "${ROOT_DIR}/index.html" "${STAGE_DIR}/index.html"

tar -C "${OUT_DIR}" -czf "${OUT_DIR}/${PACKAGE_NAME}.tar.gz" "${PACKAGE_NAME}"
printf '%s\n' "${OUT_DIR}/${PACKAGE_NAME}.tar.gz"
