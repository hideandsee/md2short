#!/usr/bin/env bash
# 성공 시 무출력, 실패 시에만 전체 출력 + 원래 종료 코드 (ralph feedback gate용).
out="$("$@" 2>&1)"; rc=$?
if [ $rc -ne 0 ]; then printf '%s\n' "$out"; fi
exit $rc
