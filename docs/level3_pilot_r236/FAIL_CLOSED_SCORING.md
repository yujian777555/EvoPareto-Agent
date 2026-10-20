# Fail-Closed Scoring (Task B)

`ok=True` now requires ALL of:
1. `container_created == True` (CID file proves the container existed)
2. `cleaned == True` (explicit `docker rm` succeeded or ALREADY_REMOVED)
3. `proc.returncode == 0`
4. `answer_text` present (valid structured result)
5. no `DOCKER_RM_FAILED` / `CLEANUP_EXCEPTION` / `CLEANUP_FN_EXCEPTION`

`CONTAINER_NOT_CREATED` can no longer score even with rc=0 and a valid
answer JSON. `ALREADY_REMOVED` requires a concrete container ID and Docker's
explicit "No such container" — daemon errors and inspect failures raise
`DockerCheckError`, never pass as "gone".

| Scenario | ok |
|---|---|
| rc=0 + valid answer + no CID | **False** |
| container created + cleaned + rc=0 + answer | True |
| container created + rm fails | **False** |
| Docker check daemon-down | raises, never passes |
