"""Privacy utilities for detecting and masking sensitive information."""

from __future__ import annotations

import re
from typing import Any

# Common secret patterns
SECRET_PATTERNS = {
    "AWS Key": r"AKIA[0-9A-Z]{16}",
    "AWS Secret": r"(?i)aws_secret_access_key[\s:=]+['\"]?([a-zA-Z0-9/+=]{40})['\"]?",
    "GitHub Token": r"gh[pous]_[a-zA-Z0-9]{36,251}",
    "OpenAI Key": r"sk-[a-zA-Z0-9]{32,}",
    "Anthropic Key": r"sk-ant-api03-[a-zA-Z0-9]{95,}",
    "Generic Token": r"(?i)(?:token|api|key|secret|password|passwd)[\s:=]+['\"]?([a-zA-Z0-9_\-\.]{16,})['\"]?",
    "Email Address": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    "Private Key": r"-----BEGIN [A-Z ]+ PRIVATE KEY-----",
}


def scan_text(text: str) -> list[dict[str, str]]:
    """Scan text for potential secrets. Returns a list of findings."""
    findings = []
    for name, pattern in SECRET_PATTERNS.items():
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            findings.append({
                "type": name,
                "match": match.group(0),
                "start": match.start(),
                "end": match.end(),
            })
    return findings


def mask_secrets(text: str) -> str:
    """Mask sensitive information in the given text."""
    masked_text = text
    # Sort findings by start position descending to avoid index shifts during replacement
    findings = sorted(scan_text(text), key=lambda x: x["start"], reverse=True)
    
    for f in findings:
        start, end = f["start"], f["end"]
        # Keep first/last 4 chars if long enough
        val = f["match"]
        if len(val) > 8:
            replacement = val[:4] + "..." + val[-4:]
        else:
            replacement = "..."
            
        masked_text = masked_text[:start] + f"[[MASKED {f['type']}: {replacement}]]" + masked_text[end:]
        
    return masked_text
