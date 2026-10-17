#!/usr/bin/env python3
"""Mock GitHub OSINT tool - test icin. Gercek tool ile ayni stdout JSON shape'i."""
import json, sys, time

target = sys.argv[1] if len(sys.argv) > 1 else ""

# Simule et - hedefe gore farkli senaryolar
if target.lower() in ("nonexistent_user_12345", "ghost404"):
    # Not-found case: tool schema'yi dondurur ama login=None
    out = {
        "scanned_at": "2026-04-21T19:30:00Z",
        "login": None, "id": None, "avatar_url": None, "name": None,
        "blog": None, "location": None, "twitter_username": None,
        "email": None, "company": None, "bio": None,
        "public_repos": None, "followers": None, "following": None,
        "created_at": None, "updated_at": None, "profile_readme": None,
        "emails_all": [], "social_accounts": [], "social_media": {},
        "organizations": [], "secrets_found": [], "sensitive_files": [],
        "public_events_emails": [], "commit_search_emails": [],
        "gist_count": 0, "GPG_ids": [], "GPG_keys": None,
        "starred_top_languages": {}, "starred_top_topics": {},
    }
else:
    # Success case - zengin veri
    time.sleep(0.3)  # fake API gecikmesi
    out = {
        "scanned_at": "2026-04-21T19:30:00Z",
        "login": target.lstrip("@").split("/")[-1] or "testuser",
        "id": 42,
        "avatar_url": f"https://avatars.githubusercontent.com/u/42?v=4",
        "name": "Test User",
        "blog": "https://example.dev",
        "location": "Istanbul, TR",
        "twitter_username": "testuser_x",
        "email": None,
        "company": "@TestOrg",
        "bio": "Security researcher. OSINT enthusiast.",
        "public_repos": 42,
        "followers": 247,
        "following": 89,
        "created_at": "2020-03-15T10:00:00Z",
        "updated_at": "2026-04-15T12:00:00Z",
        "profile_readme": "main/README.md",
        "emails_all": [
            "testuser@example.dev",
            "research@test.org",
        ],
        "social_accounts": [
            {"provider": "twitter", "url": "https://twitter.com/testuser_x"},
            {"provider": "linkedin", "url": "https://linkedin.com/in/testuser"},
        ],
        "social_media": {
            "Twitter/X": ["testuser_x"],
            "LinkedIn": ["testuser"],
            "Mastodon": ["@testuser@infosec.exchange"],
            "Keybase": ["testuser"],
        },
        "organizations": [
            {"org": "TestOrg", "members": ["alice", "bob"]},
            {"org": "AnotherOrg", "members": []},
        ],
        "secrets_found": [],
        "sensitive_files": [],
        "public_events_emails": [],
        "commit_search_emails": [
            {"email": "testuser@example.dev", "name": "Test User", "role": "author", "repo": "testuser/tool"},
        ],
        "gist_count": 3,
        "GPG_ids": ["ABCDEF1234567890"],
        "GPG_keys": f"https://github.com/{target}.gpg",
        "starred_top_languages": {"Python": 15, "Go": 8, "Rust": 3},
        "starred_top_topics": {"osint": 12, "security": 9, "python": 5},
    }

# Gercek tool gibi text + JSON karisik bas
print("─" * 52)
print(f"  GitHub Profile ({target})")
print("─" * 52)
if out["login"]:
    print(f"[+] login: {out['login']}")
    print(f"[+] name: {out['name']}")
else:
    print(f"[-] Username '{target}' does not exist.")

# En sonda JSON - _extract_last_json bunu yakalar
print(json.dumps(out, sort_keys=True, indent=4, ensure_ascii=False))
