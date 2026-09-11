"""Technical Video Mode support (spec section 26).

Detects transcript segments whose full text reads as a spoken command
or code line, so exporters can present them in a code block. This is a
narrow pattern match on common CLI tool names, not code understanding,
so it is conservative by design: it only fires on segments that read
like a whole command, minimizing false positives on ordinary prose that
happens to mention a tool by name.
"""

from __future__ import annotations

import re

_COMMAND_START = re.compile(
    r"^(sudo\s+)?"
    r"(docker|docker-compose|git|npm|npx|pip|pip3|python|python3|curl|wget|"
    r"kubectl|helm|ssh|cd|ls|mkdir|rm|cp|mv|cat|grep|chmod|chown|systemctl|"
    r"apt|apt-get|brew|yarn|cargo|go|make|terraform|ansible-playbook|node|"
    r"npm install|pip install)\b",
    re.IGNORECASE,
)


def is_code_like(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > 200:
        return False
    return bool(_COMMAND_START.match(stripped))
