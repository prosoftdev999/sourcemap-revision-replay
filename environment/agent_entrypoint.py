#!/usr/bin/env python3
import os
import sys

AGENT_UID = 10001
AGENT_GID = 10001

# Runtime log mounts are created after the image is built. Lock them before the
# agent command starts so grader-looking files cannot be planted from this
# container.
for path in ("/logs", "/logs/verifier", "/logs/artifacts"):
    try:
        os.makedirs(path, mode=0o755, exist_ok=True)
    except OSError:
        pass

for path in ("/logs/verifier", "/logs/artifacts", "/logs"):
    try:
        os.chown(path, 0, 0)
        os.chmod(path, 0o555)
    except OSError:
        pass

# Keep shipped evidence immutable while leaving /app itself writable for the
# repaired program, scratch files, and the declared result artifact.
for root, dirs, files in os.walk("/app/data"):
    try:
        os.chown(root, 0, 0)
        os.chmod(root, 0o555)
    except OSError:
        pass
    for name in files:
        path = os.path.join(root, name)
        try:
            os.chown(path, 0, 0)
            os.chmod(path, 0o444)
        except OSError:
            pass

os.setgroups([])
os.setgid(AGENT_GID)
os.setuid(AGENT_UID)

argv = sys.argv[1:] or ["sleep", "infinity"]
os.execvp(argv[0], argv)
