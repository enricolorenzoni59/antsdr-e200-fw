#!/bin/bash
# Exercise Bash-only features in the cross-built executable under qemu-arm.
set -euo pipefail
declare -A radio=([rate]=24000000 [channels]=2)
samples=(i q)
[[ ${radio[rate]} == 24000000 && ${samples[1]} == q ]]
[[ ${#samples[@]} -eq 2 ]]
if false | true; then
    printf 'pipefail did not propagate the pipeline failure\n' >&2
    exit 1
fi
printf 'Bash %s: associative arrays, indexed arrays, conditionals and pipefail enabled: PASS\n' "$BASH_VERSION"
