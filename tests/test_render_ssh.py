"""0.1.1 change 1, end to end: the installed ``nuzehub-tui --demo`` in a real pty with an ssh-like environment
(SSH_CONNECTION set, TERM=xterm-256color, TERM_PROGRAM=ghostty, no COLORTERM). The pane background must reach the
terminal as 24-bit #080e19 (``48;2;8;14;25``, HUDdy, the 0.2.0 default, softened in 0.2.3; was #0d1117), not the 256-colour index 16 (#000000). Uses only the command line,
so the same file runs against the 0.1.0 wheel to show the failure. NUZEHUB_TUI_RENDER_LOG keeps the evidence."""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
import time
from collections import Counter

TRUE_BG = b"48;2;8;14;25"  # 0.2.0: default theme HUDdy; 0.2.3: soft background #080e19
IDX16 = re.compile(rb"48;5;16[m;]")


def _run(env: dict[str, str], seconds: float = 6.0) -> bytes:
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    proc = subprocess.Popen([sys.executable, "-m", "nuzehub_tui", "--demo", "--state", env["HOME"] + "/state"],
                            stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
    os.close(slave)
    out = b""
    end = time.time() + seconds
    try:
        while time.time() < end:
            r, _, _ = select.select([master], [], [], 0.2)
            if r:
                try:
                    out += os.read(master, 65536)
                except OSError:
                    break
        os.write(master, b"q")
        time.sleep(0.5)
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        os.close(master)
    return out


def test_ssh_session_renders_true_background(tmp_path):
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8",
           "SSH_CONNECTION": "192.0.2.2 50000 192.0.2.1 22", "TERM": "xterm-256color", "TERM_PROGRAM": "ghostty"}
    out = _run(env)
    bgs = Counter(m.group(0).decode() for m in re.finditer(rb"48;(?:2;\d+;\d+;\d+|5;\d+)", out))
    log = os.environ.get("NUZEHUB_TUI_RENDER_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"python {sys.executable}\nenv TERM=xterm-256color TERM_PROGRAM=ghostty SSH_CONNECTION set, no COLORTERM\n")
            fh.write(f"bytes {len(out)}; background sequences (most common): {bgs.most_common(6)}\n")
            fh.write(f"24-bit #080e19 present: {TRUE_BG in out}; 256-colour index 16 present: {bool(IDX16.search(out))}\n")
    assert len(out) > 1000, out[:200]
    assert TRUE_BG in out, bgs.most_common(6)
    assert not IDX16.search(out), bgs.most_common(6)
