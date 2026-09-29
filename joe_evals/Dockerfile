# The throwaway sandbox the eval `Bash` tool runs in: inspection commands only.
# joe: no python and no uv, so pytest, prek and coverage output stay scripted in the case files
# The base is pinned by digest: a pull request cannot swap the image a run builds on.
FROM alpine:3.24@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6

RUN apk add --no-cache bash coreutils git grep
