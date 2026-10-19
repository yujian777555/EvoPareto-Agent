# Docker Container Cleanup (Task B)

`--cidfile` tracks the container ID. Explicit `docker rm -f` on every exit
path (normal/timeout/overflow/exception). Cleanup failures reported in
`docker_cleanup` status. 5 tests verify the specific container is gone via
`docker inspect`, not just `docker ps` rc=0.
