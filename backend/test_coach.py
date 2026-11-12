#!/usr/bin/env python3
"""Tests for the AI Coach: parsing, the prose fallback and the modes.

Run with:   ./venv/bin/python test_coach.py
Live check: ./venv/bin/python test_coach.py --live     (needs a provider key)

These tests use NO network and NO database by default. The live check talks
to the configured LLM provider and is only run when --live is passed.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_agent import (  # noqa: E402
    _build_system_prompt,
    _extract_content,
    _mode_prompt,
    _parse_coach_json,
    _tidy_sentence,
)

PASSED = 0
FAILED = 0


def check(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name}" + (f"\n        {detail}" if detail else ""))


# ---------------------------------------------------------------------
# 1. Normal JSON replies
# ---------------------------------------------------------------------
def test_json_reply():
    print("\n[1] A well-formed JSON reply is parsed")
    raw = json.dumps({
        "corrected": "I went to the office yesterday",
        "reply": "You said 'i go to office yesterday' - a more natural way to say that is 'I went to the office yesterday'.",
        "tip": "Use the past tense for finished actions.",
    })
    r = _parse_coach_json(raw, "i go to office yesterday")
    check("corrected is read", r["corrected"] == "I went to the office yesterday", r["corrected"])
    check("reply is read", "more natural way" in r["reply"], r["reply"])
    check("tip is read", r["tip"].startswith("Use the past tense"), r["tip"])


def test_json_in_code_fence():
    print("\n[2] A JSON reply wrapped in a markdown code fence is parsed")
    raw = '```json\n{"corrected": "I resigned yesterday", "reply": "That is right.", "tip": ""}\n```'
    r = _parse_coach_json(raw, "i resigned yesterday")
    check("code fence stripped", r["corrected"] == "I resigned yesterday", r["corrected"])


def test_truncated_json():
    print("\n[3] A reply truncated by the token limit still gives the fields")
    raw = '{"corrected": "I resigned from my job", "reply": "You said I just have resigned from my job - a more natural way'
    r = _parse_coach_json(raw, "I just have resigned from my job")
    check("corrected recovered", r["corrected"] == "I resigned from my job", r["corrected"])
    check("reply is never empty", bool(r["reply"].strip()), repr(r["reply"]))


# ---------------------------------------------------------------------
# 2. The prose fallback - the bug that produced
#    "That sounds good. Try another sentence and I will check it."
# ---------------------------------------------------------------------
PROSE_CASES = [
    (
        "the interviewer asked me about my weakness",
        "You said the interviewer asked me about my weakness - a more natural way to say that is The interviewer asked me about my weakness. What kind of weaknesses do you usually talk about?",
        "The interviewer asked me about my weakness",
    ),
    (
        "I just have resigned from my job",
        "You said I just have resigned from my job - a more natural way to say that is I just resigned from my job What are you planning to do next?",
        "I just resigned from my job",
    ),
    (
        "I moved from Bangalore to Mumbai last year",
        "You said I moved from Bangalore to Mumbai last year - a more natural way to say that is I moved from Bangalore to Mumbai last year. Where are you based now?",
        "I moved from Bangalore to Mumbai last year",
    ),
    (
        "i go to office yesterday",
        "You said 'i go to office yesterday' - a more natural way to say that is 'I went to the office yesterday'.",
        "I went to the office yesterday",
    ),
]


def test_prose_fallback():
    print("\n[4] A prose reply is salvaged instead of being thrown away")
    for user_text, prose, expected in PROSE_CASES:
        r = _parse_coach_json(prose, user_text)
        check(f"corrected from prose: {user_text[:38]!r}", r["corrected"] == expected,
              f"got {r['corrected']!r}, expected {expected!r}")
        check("the fallback reply is NOT used",
              r["reply"] != "That sounds good. Try another sentence and I will check it.",
              r["reply"][:80])


def test_prose_keeps_proper_nouns():
    print("\n[5] A proper noun is not truncated by the question cut")
    user_text = "I moved from Bangalore to Mumbai last year"
    prose = ("You said I moved from Bangalore to Mumbai last year - a more natural way to say that is "
             "I moved from Bangalore to Mumbai last year. Where are you based now?")
    r = _parse_coach_json(prose, user_text)
    check("city names survive", "Bangalore" in r["corrected"] and "Mumbai" in r["corrected"], r["corrected"])


def test_empty_output():
    print("\n[6] An empty model answer still returns something usable")
    r = _parse_coach_json("", "hello")
    check("corrected is not empty", bool(r["corrected"].strip()), repr(r["corrected"]))
    check("reply is not empty", bool(r["reply"].strip()), repr(r["reply"]))
    check("no raw JSON is spoken", not r["reply"].strip().startswith("{"), r["reply"][:60])


# ---------------------------------------------------------------------
# 3. Capitalisation
# ---------------------------------------------------------------------
def test_capitalisation():
    print("\n[7] A capitalisation-only correction is kept")
    check("first letter is capitalised", _tidy_sentence("my weakness is slow") == "My weakness is slow")
    check("already capital text is untouched", _tidy_sentence("My weakness is slow") == "My weakness is slow")
    check("empty stays empty", _tidy_sentence("") == "")
    check("a leading quote is not mangled", _tidy_sentence("'hello") == "'hello")


# ---------------------------------------------------------------------
# 4. The prompt: modes and the JSON reinforcement
# ---------------------------------------------------------------------
def test_modes():
    print("\n[8] Each mode adds its own overlay")
    check("practice has no overlay", _mode_prompt("practice") == "")
    check("interview has an overlay", "INTERVIEW MODE" in _mode_prompt("interview"))
    check("jobsearch has an overlay", "JOB SEARCH MODE" in _mode_prompt("jobsearch"))
    check("an unknown mode falls back to practice", _mode_prompt("nonsense") == "")
    check("mode is case-insensitive", "INTERVIEW MODE" in _mode_prompt("Interview"))


def test_system_prompt():
    print("\n[9] The system prompt restates the JSON contract once there is history")
    first_turn = _build_system_prompt("practice", False)
    later_turn = _build_system_prompt("practice", True)
    check("turn 1 has no reinforcement", "you are in the middle of a conversation" not in first_turn.lower())
    check("turn 2 has the reinforcement", "you are in the middle of a conversation" in later_turn.lower())
    check("the reinforcement demands JSON", "raw JSON object" in later_turn)
    check("the mode overlay is in the prompt", "INTERVIEW MODE" in _build_system_prompt("interview", False))
    check("the base prompt is always there", "A2M Coach" in first_turn)


def test_extract_content():
    print("\n[10] An empty model answer is reported as an error, not as the text 'None'")
    try:
        _extract_content({"choices": [{"message": {"content": None, "reasoning_content": "thinking..."}}]})
        check("an empty answer raises", False, "no exception was raised")
    except Exception as exc:
        check("an empty answer raises", True)
        check("the reason mentions the token budget", "max_tokens" in str(exc), str(exc))
    check("normal content is returned",
          _extract_content({"choices": [{"message": {"content": "hello"}}]}) == "hello")


# ---------------------------------------------------------------------
# 5. Live check against the real provider
# ---------------------------------------------------------------------
LIVE_TURNS = [
    "I just have resigned from my job",
    "my weakness is i work slowly sometimes",
    "the interviewer asked me about my weakness",
]


def test_live():
    print("\n[11] LIVE: a 3-turn conversation against the configured provider")
    from ai_agent import coach_reply

    async def run():
        history = []
        for text in LIVE_TURNS:
            result = await coach_reply(text, history)
            print(f"\n      >>> {text}")
            print(f"      corrected: {result['corrected']}")
            print(f"      reply    : {result['reply'][:120]}")
            check(f"a real correction came back for {text[:30]!r}",
                  result["corrected"].strip() and
                  result["corrected"] != "That sounds good. Try another sentence and I will check it.",
                  result["corrected"])
            check("the reply is not the fallback",
                  result["reply"] != "That sounds good. Try another sentence and I will check it.",
                  result["reply"][:80])
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": json.dumps({
                "corrected": result["corrected"],
                "reply": result["reply"],
                "tip": result["tip"],
            })})

    asyncio.run(run())


def main():
    test_json_reply()
    test_json_in_code_fence()
    test_truncated_json()
    test_prose_fallback()
    test_prose_keeps_proper_nouns()
    test_empty_output()
    test_capitalisation()
    test_modes()
    test_system_prompt()
    test_extract_content()
    if "--live" in sys.argv:
        test_live()

    print("\n" + "=" * 60)
    print(f"PASSED {PASSED}   FAILED {FAILED}")
    print("=" * 60)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
