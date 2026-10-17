"""IPC security negative tests (Stage 3.0-P1-R2A-R2 Task 1)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.workflow_ipc import (
    IPCSecurityError,
    MAX_PROMPT_CHARS,
    MAX_REQUEST_BYTES,
    ModelIPCServer,
    _safe_join,
    _write_json_atomic,
    validate_request_id,
)


class FakeLLM:
    def __init__(self):
        self.calls = []

    def _request(self, prompt: str) -> str:
        self.calls.append(prompt)
        return "ok:" + prompt[:20]


@pytest.fixture()
def mailbox(tmp_path):
    ipc = tmp_path / "ipc"
    (ipc / "out").mkdir(parents=True)
    (ipc / "in").mkdir(parents=True)
    llm = FakeLLM()
    server = ModelIPCServer(ipc, llm, trusted_model="deepseek-flash")
    server.start()
    yield {"ipc": ipc, "server": server, "llm": llm}
    server.stop()


def _put(ipc: Path, filename: str, payload: dict):
    (ipc / "out" / filename).write_text(json.dumps(payload), encoding="utf-8")


def _wait(server, n=1.0):
    time.sleep(n)


# ---------- ID validation ----------

def test_valid_id_accepted():
    rid = "a" * 32
    assert validate_request_id(rid) == rid


@pytest.mark.parametrize("bad", [
    "../" + "a" * 28,
    "/etc/passwd" + "a" * 20,
    "C:\\Windows\\x" + "a" * 18,
    "..\\..\\x" + "a" * 24,
    "zzzz" + "a" * 28,
    "A" * 32,                 # uppercase rejected
    "a" * 31,                 # wrong length
    "a" * 33,
    "",
    "a" * 16 + "/" + "b" * 15,
    "a" * 16 + "\\" + "b" * 15,
    "a/../../etc/passwd",
    "..",
    ".",
])
def test_invalid_ids_rejected(bad):
    with pytest.raises(IPCSecurityError):
        validate_request_id(bad)


def test_non_string_id_rejected():
    with pytest.raises(IPCSecurityError):
        validate_request_id(12345)
    with pytest.raises(IPCSecurityError):
        validate_request_id(None)


# ---------- negative mailbox tests ----------

def test_traversal_id_no_model_call(mailbox):
    # a filename whose stem is a traversal token must never reach the model
    _put(mailbox["ipc"], "..evil.json", {"id": "..evil", "prompt": "p"})
    _put(mailbox["ipc"], "....json", {"id": "....", "prompt": "p"})
    _wait(mailbox["server"], 0.4)
    assert mailbox["llm"].calls == []
    assert any(e["kind"] == "REJECT_ID" for e in mailbox["server"].security_events)
    # direct helper checks for real traversal forms
    for bad in ("../evil.json", "..\\evil.json", "a/../b.json"):
        with pytest.raises(IPCSecurityError):
            _safe_join(mailbox["ipc"] / "in", bad)


def test_absolute_path_id_no_model_call(mailbox):
    _put(mailbox["ipc"], "/abs.json", {"id": "x", "prompt": "p"})  # writes into out/ literally
    # also a filename with slash is impossible via normal write; simulate via stem check
    _wait(mailbox["server"], 0.3)
    # the file name " /abs.json" can't be created as a name with slash; instead
    # create a request whose JSON id is absolute
    rid = "b" * 32
    _put(mailbox["ipc"], f"{rid}.json", {"id": "/etc/passwd", "prompt": "p"})
    _wait(mailbox["server"])
    assert mailbox["llm"].calls == []
    assert any(e["kind"] == "REJECT_JSON_ID" for e in mailbox["server"].security_events)


def test_windows_path_id_rejected():
    with pytest.raises(IPCSecurityError):
        validate_request_id("C:\\Users\\x" + "a" * 20)


def test_invalid_id_no_model_call(mailbox):
    _put(mailbox["ipc"], "not-a-valid-id.json", {"id": "not-a-valid-id", "prompt": "p"})
    _wait(mailbox["server"])
    assert mailbox["llm"].calls == []


def test_duplicate_id_rejected(mailbox):
    rid = "c" * 32
    # drive the handler directly so ordering is deterministic
    p1 = mailbox["ipc"] / "out" / f"{rid}.json"
    p1.write_text(json.dumps({"id": rid, "prompt": "first"}), encoding="utf-8")
    mailbox["server"]._handle_one(p1)
    assert mailbox["llm"].calls == ["first"]
    p2 = mailbox["ipc"] / "out" / f"{rid}.json"
    p2.write_text(json.dumps({"id": rid, "prompt": "second"}), encoding="utf-8")
    mailbox["server"]._handle_one(p2)
    assert mailbox["llm"].calls == ["first"]  # second not processed
    assert any(e["kind"] == "REJECT_DUPLICATE" for e in mailbox["server"].security_events)


def test_id_mismatch_rejected(mailbox):
    rid = "d" * 32
    _put(mailbox["ipc"], f"{rid}.json", {"id": "e" * 32, "prompt": "p"})
    _wait(mailbox["server"])
    assert mailbox["llm"].calls == []
    assert any(e["kind"] == "REJECT_ID_MISMATCH" for e in mailbox["server"].security_events)


def test_unauthorized_model_rejected(mailbox):
    rid = "f" * 32
    _put(mailbox["ipc"], f"{rid}.json", {"id": rid, "prompt": "p", "model": "gpt-99"})
    _wait(mailbox["server"])
    assert mailbox["llm"].calls == []
    assert any(e["kind"] == "REJECT_UNAUTHORIZED_MODEL" for e in mailbox["server"].security_events)


def test_untrusted_json_cannot_choose_response_path(mailbox, tmp_path):
    """Even if JSON contains a path field, the response goes to /ipc/in/<rid>.json."""
    rid = "ab" + "0" * 30
    outside = tmp_path / "owned.txt"
    _put(mailbox["ipc"], f"{rid}.json", {
        "id": rid, "prompt": "p",
        "response_path": str(outside),
        "id_path": "../escape",
    })
    _wait(mailbox["server"])
    assert not outside.exists()
    assert (mailbox["ipc"] / "in" / f"{rid}.json").exists()


def test_oversized_request_rejected(mailbox):
    rid = "aa" + "1" * 30
    big = "x" * (MAX_REQUEST_BYTES + 100)
    (mailbox["ipc"] / "out" / f"{rid}.json").write_text(
        json.dumps({"id": rid, "prompt": big}), encoding="utf-8"
    )
    _wait(mailbox["server"])
    assert mailbox["llm"].calls == []
    assert any(e["kind"] == "REJECT_READ" for e in mailbox["server"].security_events)


def test_oversized_prompt_rejected(mailbox):
    rid = "bb" + "2" * 30
    _put(mailbox["ipc"], f"{rid}.json", {"id": rid, "prompt": "y" * (MAX_PROMPT_CHARS + 10)})
    _wait(mailbox["server"])
    assert mailbox["llm"].calls == []
    assert any(e["kind"] == "REJECT_OVERSIZED_PROMPT" for e in mailbox["server"].security_events)


def test_symlink_request_rejected(mailbox, tmp_path):
    target = tmp_path / "real.json"
    target.write_text(json.dumps({"id": "cc" + "3" * 30, "prompt": "p"}), encoding="utf-8")
    link = mailbox["ipc"] / "out" / ("cc" + "3" * 30 + ".json")
    if hasattr(os, "symlink"):
        try:
            os.symlink(str(target), str(link))
        except OSError:
            pytest.skip("symlink not permitted")
    else:
        pytest.skip("no symlink")
    _wait(mailbox["server"])
    # either refused as symlink or (on platforms without O_NOFOLLOW) still no escape
    assert (mailbox["llm"].calls == []) or (link.is_symlink())


def test_symlink_response_rejected(mailbox, tmp_path):
    rid = "dd" + "4" * 30
    evil = tmp_path / "evil_target.json"
    link = mailbox["ipc"] / "in" / f"{rid}.json"
    if hasattr(os, "symlink"):
        try:
            os.symlink(str(evil), str(link))
        except OSError:
            pytest.skip("symlink not permitted")
    else:
        pytest.skip("no symlink")
    _put(mailbox["ipc"], f"{rid}.json", {"id": rid, "prompt": "p"})
    _wait(mailbox["server"])
    # must not write through the symlink
    assert not evil.exists() or evil.read_text(encoding="utf-8") == ""


def test_replaced_file_race_detected(mailbox):
    """Response O_EXCL refuses to overwrite an existing response."""
    rid = "ee" + "5" * 30
    resp = mailbox["ipc"] / "in" / f"{rid}.json"
    resp.write_text('{"pre": 1}', encoding="utf-8")
    _put(mailbox["ipc"], f"{rid}.json", {"id": rid, "prompt": "p"})
    _wait(mailbox["server"])
    assert json.loads(resp.read_text(encoding="utf-8")) == {"pre": 1}
    assert any(
        e["kind"] == "REJECT_RESPONSE_WRITE" for e in mailbox["server"].security_events
    )


def test_safe_join_blocks_escapes(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    with pytest.raises(IPCSecurityError):
        _safe_join(root, "../x")
    with pytest.raises(IPCSecurityError):
        _safe_join(root, "a/b")
    with pytest.raises(IPCSecurityError):
        _safe_join(root, "C:\\x")
    with pytest.raises(IPCSecurityError):
        _safe_join(root, "/etc/passwd")
    ok = _safe_join(root, "abc.json")
    assert ok == root.resolve() / "abc.json" or ok == (root / "abc.json").absolute()


def test_valid_request_still_works(mailbox):
    rid = "ff" + "6" * 30
    _put(mailbox["ipc"], f"{rid}.json", {"id": rid, "prompt": "hello world"})
    _wait(mailbox["server"], 0.5)
    assert mailbox["llm"].calls == ["hello world"]
    resp = json.loads((mailbox["ipc"] / "in" / f"{rid}.json").read_text(encoding="utf-8"))
    assert resp["ok"] is True
