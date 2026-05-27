import pytest
from carbonclaw.utils.privacy import scan_text, mask_secrets

def test_secret_scanning():
    # Correct Anthropic key format: sk-ant-api03-... (95 chars total)
    # The regex is sk-ant-api03-[a-zA-Z0-9]{95,}
    # "sk-ant-api03-" is 13 chars. We need 95 MORE chars.
    anthropic_key = "sk-ant-api03-" + "A" * 95
    text = f"My key is {anthropic_key} and email is test@example.com"
    findings = scan_text(text)
    
    types = [f["type"] for f in findings]
    assert "Anthropic Key" in types
    assert "Email Address" in types

def test_secret_masking():
    # Use a pattern that doesn't overlap with Generic Token
    text = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    masked = mask_secrets(text)
    
    assert "[[MASKED GitHub Token:" in masked
    assert "ghp_...6789" in masked
