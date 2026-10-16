# Archive Safety Audit

Real archive: 1720 members, SHA-256 F460F9C9218216F6…

Negative tests (crafted malicious tars): {"traversal": "REJECTED:TRAVERSAL:../escape.txt", "symlink": "REJECTED:LINK:link", "absolute": "REJECTED:ABSOLUTE_PATH:/abs.txt", "overwrite": "REJECTED:OVERWRITE:a.txt"}

`all_rejected = True` — safe_extract enforces: absolute-path
reject, `..` reject, symlink/hardlink reject, special-file reject, per-file
50MB / total 200MB / 50k-file limits, final-path containment, no overwrite.
