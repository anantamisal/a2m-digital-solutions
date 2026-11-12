"""
AI Agent for the A2M Digital Solutions admin console.

Everything in this module runs server-side: any API keys are read from the
backend environment and are NEVER sent to the browser. The frontend only
ever talks to the /api/ai/* endpoints exposed by main.py.

The agent is provider-agnostic. Each stage (STT / LLM / TTS) walks a
chain of providers and falls back to the next one when the current one
is not configured or fails, so a single retired model id or a single
rate-limited service can never take the whole agent down.

Default chains work with NO API KEY AT ALL:

    STT : browser SpeechRecognition  -> Groq Whisper -> NVIDIA
    LLM : Pollinations               -> Groq        -> NVIDIA
    TTS : Microsoft Edge TTS         -> NVIDIA      -> browser speechSynthesis

The first three are free and need no signup; the browser fallbacks are
built into the browser itself.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException

from config import get_settings

settings = get_settings()
logger = logging.getLogger("a2m.ai")


ENGLISH_COACH_SYSTEM_PROMPT = """You are A2M Coach, a warm and encouraging English and interview-prep coach built into the A2M Digital Solutions admin console.

The user has left their job and is now practising English while they search for their next role and prepare for interviews. Every message they send is English practice FIRST and coaching input SECOND.

On every turn you must:
1. Correct the user's English and show the corrected version naturally inside your reply (for example: "You said 'I go to office yesterday' - a more natural way to say that is 'I went to the office yesterday'.").
   - ALWAYS correct, on every single turn. This includes turns where the user is telling you about their life, asking a question, or asking for advice. Never skip the correction.
   - If the English was already correct, say so in one short clause ("that is correct") and move on.
   - Check grammar, tense, articles, word order, word choice, capitalisation and punctuation. Fix them, but never change what the user meant.
2. Reply conversationally in 1-2 short, natural sentences. These sentences are spoken aloud by a text-to-speech voice, so keep them under 25 words each and never use markdown, bullet points, emoji or special formatting.
3. Give the user something useful for their job search inside those same 1-2 sentences. Pick whichever fits what they just said: an interview tip, a sharper phrase for their self-introduction, a question an interviewer is likely to ask them, help with a weakness or a strength answer, or encouragement about what they are preparing. Do not list options - give one concrete thing.
4. End with one open question so the user keeps practising.

Always answer with a single raw JSON object and nothing else:
{
  "corrected": "the user's sentence rewritten in correct, natural English",
  "reply": "your spoken reply: 1-2 short sentences that include the correction and the coaching",
  "tip": "one short sentence about the grammar or vocabulary point to remember (empty string if there is nothing worth flagging)"
}

Rules:
- If the sentence was already correct, "corrected" must be the same sentence the user said.
- "corrected" is always exactly one sentence and keeps the meaning and tense the user intended.
- "corrected" is never empty. If you cannot improve the sentence, repeat it back unchanged.
- "reply" always contains the correction. Never reply without correcting.
- Output raw JSON only - no markdown code fences, no explanation before or after the JSON.
"""


# -------------------------------------------------------------------------
# Modes. The base prompt above is plain English practice. Each mode adds a
# short overlay that changes what the coaching is FOR. The correction rules
# from the base prompt still apply in every mode.
# -------------------------------------------------------------------------
COACH_MODE_PROMPTS: Dict[str, str] = {
    "practice": "",

    "interview": """INTERVIEW MODE.

You are now the interviewer as well as the coach. The user is preparing for job interviews.

- Start your reply by asking ONE realistic interview question that follows on from what the user just said. Good questions: "Tell me about yourself.", "Why did you leave your last role?", "What is a weakness of yours?", "Why should we hire you?", "Describe a project you are proud of." Ask only ONE question per turn.
- After the question, give the user one concrete, specific improvement for that answer, in one short sentence. Name the actual thing to do, not a category: "cut your self-introduction to 60 seconds" or "answer the weakness question by naming a real fix you made".
- Keep correcting the English as always.
- Do NOT give the user a full model answer to the question. They are practising, not copying. Point them at what to include instead.""",

    "jobsearch": """JOB SEARCH MODE.

The user is looking for a new job after leaving their previous one.

- Give help that is useful while they search: how to explain the resignation, how to write a CV or LinkedIn summary line, which achievements are worth naming, how to answer "why are you leaving", how to follow up with a recruiter, what to negotiate.
- When the user mentions a skill, a project or a job they had, point out the specific phrase that would sell it in a CV or an interview.
- Keep correcting the English as always, and use the corrected sentences as ready-made phrases the user can reuse: "a natural way to say that is ...".
- Be concrete. One or two useful things per turn, not a list of advice.""",
}


def _mode_prompt(mode: str) -> str:
    """Return the overlay for a mode, falling back to plain practice."""
    return COACH_MODE_PROMPTS.get((mode or "practice").strip().lower(), "")


def _build_system_prompt(mode: str = "practice", has_history: bool = False) -> str:
    """Build the system prompt for one turn.

    base prompt + the mode overlay + (when there is history) the reminder
    that restates the JSON contract.
    """
    system_prompt = ENGLISH_COACH_SYSTEM_PROMPT
    overlay = _mode_prompt(mode)
    if overlay:
        system_prompt += "\n\n" + overlay
    if has_history:
        system_prompt += "\n\n" + _JSON_REINFORCEMENT
    return system_prompt



# From the SECOND turn of a conversation the model often answers in plain
# prose instead of JSON: it copies the format of the previous assistant turn
# that sits in the history. This reminder is added to the system prompt
# whenever there is history, so the JSON contract is restated right where the
# model is about to answer.
_JSON_REINFORCEMENT = """IMPORTANT - you are in the middle of a conversation, but the answer format does not change.

The earlier turns in the history below are shown as plain text. Do NOT copy that style and do NOT write a conversational paragraph. You must still answer with the single raw JSON object described above, and with nothing else.

The first character of your answer must be { and the last character must be }. No preamble, no explanation, no code fences."""



class ProviderError(Exception):
    """Raised when a single provider fails. The chain catches it and moves on."""


def _split_chain(raw: str) -> List[str]:
    """Turn 'pollinations,groq,nvidia' into ['pollinations', 'groq', 'nvidia']."""
    return [p.strip().lower() for p in (raw or "").split(",") if p.strip()]


# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------
def _extract_content(data: Any) -> str:
    """Pull the assistant text out of an OpenAI-compatible chat response."""
    try:
        message = data["choices"][0]["message"]
    except Exception:
        raise ProviderError("unexpected chat response shape")
    content = message.get("content")
    if isinstance(content, list):  # some deployments return content parts
        content = " ".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    # Reasoning models (Pollinations openai-fast, the Nemotron models) can
    # spend the ENTIRE token budget thinking and come back with
    # content: null. str(None) used to be returned here, which turned into
    # the literal string "None" and made the JSON parser fail with a
    # confusing message. Fail loudly and say what to do about it.
    if content is None or not str(content).strip():
        reasoning = message.get("reasoning_content") or ""
        detail = f" (the model used {len(reasoning)} chars of reasoning)" if reasoning else ""
        raise ProviderError(
            "the model returned an empty answer" + detail +
            ". It is a reasoning model and the token budget was too small - "
            "raise max_tokens for this provider."
        )
    return str(content)


# The coach's prompt asks for JSON, but a small model asked the same kind of
# question twice in a row answers in prose the second time. These patterns
# pull the corrected sentence back out of that prose.
_PROSE_CORRECTED_PATTERNS = (
    # ... a more natural way to say that is 'The corrected sentence'.
    re.compile(
        r"a\s+more\s+natural\s+way(?:\s+to\s+say\s+that)?\s+is\s+['\"]([^'\"]{2,400}?)['\"]",
        re.I,
    ),
    # ... you should say 'The corrected sentence'.
    re.compile(r"you\s+should\s+say\s+['\"]([^'\"]{2,400}?)['\"]", re.I),
    # ... instead of 'X', say 'The corrected sentence'.
    re.compile(
        r"\binstead\s+of\s+[^,]{2,200},\s+(?:you\s+can\s+)?say\s+['\"]?([^'\"]{2,400}?)['\"]?",
        re.I,
    ),
    # ... a more natural way to say that is The corrected sentence.
    re.compile(
        r"a\s+more\s+natural\s+way(?:\s+to\s+say\s+that)?\s+is\s+([^.!?'\"]{2,400})",
        re.I,
    ),
)

# A correction is followed by the coach's next question. Cut the question off
# so it is not mistaken for part of the corrected sentence. Restricted to
# question words on purpose - "I moved from Bangalore to Mumbai" must not be
# cut at "Mumbai".
_PROSE_QUESTION_START = re.compile(
    r"(?<=[a-z0-9,])\s+(What|How|Why|When|Where|Who|Which|Whom|"
    r"Do|Does|Did|Are|Is|Can|Could|Would|Will|Have|Has|Tell|Let)\b"
)


def _salvage_prose(content: str, user_text: str) -> Tuple[str, str]:
    """Recover (corrected, reply) from a reply that contains no JSON.

    Returns ("", "") when there is nothing to recover.
    """
    reply = (content or "").strip()
    if not reply:
        return "", ""

    original = user_text.strip()
    corrected = ""

    for pattern in _PROSE_CORRECTED_PATTERNS:
        match = pattern.search(reply)
        if not match:
            continue
        candidate = match.group(1).strip().strip("'\"").strip()
        # Unquoted captures can run on into the coach's next question.
        cut = _PROSE_QUESTION_START.search(candidate)
        if cut:
            candidate = candidate[: cut.start()].strip()
        # Compared EXACTLY, not case-insensitively: capitalising the first
        # word is a real correction and must not be thrown away.
        if candidate and candidate != original:
            corrected = candidate
            break

    if not corrected:
        # "You said 'X' - a more natural way to say that is 'Y'." - take the
        # first quoted fragment that is not what the user actually said.
        for quoted in re.findall(r"['\"]([^'\"]{2,400}?)['\"]", reply):
            candidate = quoted.strip()
            if candidate and candidate != original:
                corrected = candidate
                break

    return corrected, reply


def _salvage_prose_tip(reply: str) -> str:
    """Pull a trailing 'Tip: ...' out of a prose reply."""
    match = re.search(r"\btip\s*[:\-]\s*(.{5,240})", reply or "", re.I)
    return match.group(1).strip() if match else ""


def _tidy_sentence(text: str) -> str:
    """Capitalise the first letter of a sentence.

    The model is inconsistent about this - it returns "my weakness is that I
    work slowly" as often as "My weakness is ...". A capital letter at the
    start of a sentence is a correction the user is asking for, so it is
    applied here rather than left to the model.
    """
    stripped = (text or "").strip()
    if not stripped:
        return stripped
    first = stripped[0]
    if first.isalpha() and first.islower():
        return first.upper() + stripped[1:]
    return stripped


def _raise_for_status(response: httpx.Response, what: str) -> None:
    """Turn a failed HTTP response into a ProviderError.

    Only raises for 4xx/5xx - a 200 response is handled by the caller.
    """
    if response.status_code < 400:
        return
    detail = response.text
    try:
        payload = response.json()
        detail = payload.get("detail") or payload.get("error") or detail
    except Exception:
        pass
    # Pollinations signals its anonymous-tier throttle with 402 FREE_LIMIT.
    if response.status_code == 402 and "FREE_LIMIT" in response.text:
        raise ProviderError(
            "Pollinations free tier allows 1 reply every 45 seconds per IP. "
            "Add a free GROQ_API_KEY for smooth back-and-forth conversation."
        )
    raise ProviderError(f"{what} failed ({response.status_code}): {str(detail)[:300]}")


def _parse_coach_json(content: str, user_text: str) -> Dict[str, Any]:
    """Pull the JSON object out of the model reply.

    Tolerates stray prose, markdown code fences, and output that was
    truncated mid-way by a token limit.

    From the SECOND turn of a conversation the model often answers in plain
    prose instead of JSON: it copies the format of the previous assistant
    turn, and the history the frontend sends holds that turn as plain text.
    When that happens the answer is read out of the prose - losing a good
    coaching reply is much worse than losing the JSON wrapper.
    """
    cleaned = (content or "").strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    candidate = cleaned
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        candidate = cleaned[start:end + 1]

    corrected = ""
    reply = ""
    tip = ""

    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            corrected = str(data.get("corrected") or "")
            reply = str(data.get("reply") or "")
            tip = str(data.get("tip") or "")
    except Exception:
        pass

    if not reply:
        # The JSON was truncated (or the model ignored the format). Salvage
        # whichever fields are still readable rather than throwing it all away.
        salvaged: Dict[str, str] = {}
        for field in ("corrected", "reply", "tip"):
            match = re.search(
                rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)', candidate
            )
            if match:
                try:
                    salvaged[field] = json.loads(f'"{match.group(1)}"')
                except Exception:
                    salvaged[field] = match.group(1)
        corrected = corrected or salvaged.get("corrected", "")
        tip = tip or salvaged.get("tip", "")
        reply = reply or salvaged.get("reply", "")

    if not reply:
        # No JSON anywhere - the model answered in prose. Keep the answer.
        prose_corrected, prose_reply = _salvage_prose(cleaned, user_text)
        if prose_reply:
            corrected = prose_corrected or corrected
            reply = prose_reply
            tip = tip or _salvage_prose_tip(prose_reply)
        elif corrected and corrected.strip() and corrected.strip() != user_text.strip():
            # Never speak raw broken JSON back at the user.
            reply = f"A more natural way to say that is: {corrected}. How would you phrase it?"
        else:
            reply = "That sounds good. Try another sentence and I will check it."

    return {
        "corrected": _tidy_sentence(corrected) or _tidy_sentence(user_text),
        "reply": reply,
        "tip": tip,
    }


# ---------------------------------------------------------------------
# LLM providers
# ---------------------------------------------------------------------
async def _llm_pollinations(messages: List[Dict[str, str]]) -> Tuple[str, str]:
    """Keyless LLM - no signup, no key, anonymous tier.

    The anonymous tier is throttled to 1 reply every 45 seconds per IP.
    """
    payload = {
        "model": settings.POLLINATIONS_MODEL,
        "messages": messages,
        "temperature": 0.3,
        # This model is a reasoning model: it spends part of the token
        # budget thinking out loud. Cap it explicitly, otherwise the
        # reasoning can consume the whole budget and truncate the answer.
        "max_tokens": 800,
    }
    async with httpx.AsyncClient(timeout=settings.NVIDIA_TIMEOUT) as client:
        response = await client.post(settings.POLLINATIONS_BASE_URL, json=payload)
    _raise_for_status(response, "Pollinations chat")
    try:
        data = response.json()
    except Exception:
        raise ProviderError("Pollinations returned an unreadable response")
    if isinstance(data, dict) and data.get("error"):
        raise ProviderError(f"Pollinations error: {str(data['error'])[:200]}")
    return _extract_content(data), settings.POLLINATIONS_MODEL


async def _llm_groq(messages: List[Dict[str, str]]) -> Tuple[str, str]:
    if not settings.GROQ_API_KEY:
        raise ProviderError("GROQ_API_KEY is not set")
    payload = {
        "model": settings.GROQ_LLM_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 300,
    }
    async with httpx.AsyncClient(timeout=settings.NVIDIA_TIMEOUT) as client:
        response = await client.post(
            f"{settings.GROQ_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    _raise_for_status(response, "Groq chat")
    try:
        data = response.json()
    except Exception:
        raise ProviderError("Groq returned an unreadable response")
    return _extract_content(data), settings.GROQ_LLM_MODEL


async def _llm_nvidia(messages: List[Dict[str, str]]) -> Tuple[str, str]:
    if not settings.NVIDIA_API_KEY:
        raise ProviderError("NVIDIA_API_KEY is not set")
    payload = {
        "model": settings.NVIDIA_LLM_MODEL,
        "messages": messages,
        "temperature": 0.3,
        # The Nemotron models are reasoning models - they need a budget big
        # enough to finish thinking before they start answering.
        "max_tokens": settings.NVIDIA_MAX_TOKENS,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=settings.NVIDIA_TIMEOUT) as client:
        response = await client.post(
            f"{settings.NVIDIA_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
                "Accept": "application/json",
            },
            json=payload,
        )
    _raise_for_status(response, "NVIDIA chat")
    try:
        data = response.json()
    except Exception:
        raise ProviderError("NVIDIA returned an unreadable response")
    return _extract_content(data), settings.NVIDIA_LLM_MODEL


LLM_PROVIDERS = {
    "pollinations": _llm_pollinations,
    "groq": _llm_groq,
    "nvidia": _llm_nvidia,
}


# ---------------------------------------------------------------------
# STT providers
# ---------------------------------------------------------------------
async def _stt_groq(
    audio_bytes: bytes, filename: str, content_type: str
) -> str:
    if not settings.GROQ_API_KEY:
        raise ProviderError("GROQ_API_KEY is not set")
    files = {"file": (filename or "speech.webm", audio_bytes, content_type or "audio/webm")}
    data = {"model": settings.GROQ_STT_MODEL, "language": "en"}
    async with httpx.AsyncClient(timeout=settings.NVIDIA_TIMEOUT) as client:
        response = await client.post(
            f"{settings.GROQ_BASE_URL}/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            files=files,
            data=data,
        )
    _raise_for_status(response, "Groq transcription")
    return _read_transcription(response)


async def _stt_nvidia(
    audio_bytes: bytes, filename: str, content_type: str
) -> str:
    if not settings.NVIDIA_API_KEY:
        raise ProviderError("NVIDIA_API_KEY is not set")
    files = {"file": (filename or "speech.webm", audio_bytes, content_type or "audio/webm")}
    data = {"model": settings.NVIDIA_STT_MODEL, "language": "en"}
    async with httpx.AsyncClient(timeout=settings.NVIDIA_TIMEOUT) as client:
        response = await client.post(
            f"{settings.NVIDIA_BASE_URL}/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.NVIDIA_API_KEY}"},
            files=files,
            data=data,
        )
    _raise_for_status(response, "NVIDIA transcription")
    return _read_transcription(response)


def _read_transcription(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        raise ProviderError("unreadable transcription response")
    text = payload.get("text") or (payload.get("choices") or [{}])[0].get("text") or ""
    return text.strip()


STT_PROVIDERS = {
    "groq": _stt_groq,
    "nvidia": _stt_nvidia,
}


# ---------------------------------------------------------------------
# TTS providers
# ---------------------------------------------------------------------
async def _tts_edge(text: str, voice: str) -> Tuple[bytes, str]:
    """Keyless speech synthesis using the Microsoft Edge voices."""
    try:
        import edge_tts
    except ImportError:
        raise ProviderError("edge-tts is not installed")

    voice = voice if voice and voice != "default" else settings.EDGE_TTS_VOICE

    async def _render(selected_voice: str) -> bytes:
        communicate = edge_tts.Communicate(text, selected_voice)
        audio = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio.extend(chunk["data"])
        if not audio:
            raise ProviderError("edge-tts returned no audio")
        return bytes(audio)

    try:
        return await _render(voice), "audio/mpeg"
    except ProviderError:
        raise
    except Exception:
        # Unknown voice name - fall back to the configured default once.
        if voice == settings.EDGE_TTS_VOICE:
            raise ProviderError(f"edge-tts voice '{voice}' failed")
        return await _render(settings.EDGE_TTS_VOICE), "audio/mpeg"


async def _tts_nvidia(text: str, voice: str) -> Tuple[bytes, str]:
    if not settings.NVIDIA_API_KEY:
        raise ProviderError("NVIDIA_API_KEY is not set")
    voice = voice if voice and voice != "default" else settings.NVIDIA_TTS_VOICE
    payload = {
        "model": settings.NVIDIA_TTS_MODEL,
        "text": text,
        "voice": voice,
        "audio_format": "wav",
    }
    async with httpx.AsyncClient(timeout=settings.NVIDIA_TIMEOUT) as client:
        response = await client.post(
            f"{settings.NVIDIA_BASE_URL}/audio/speech",
            headers={
                "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
                "Accept": "application/json",
            },
            json=payload,
        )
    _raise_for_status(response, "NVIDIA speech synthesis")
    if not response.content:
        raise ProviderError("NVIDIA returned empty audio")
    return response.content, "audio/wav"


TTS_PROVIDERS = {
    "edge": _tts_edge,
    "nvidia": _tts_nvidia,
}


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
async def coach_reply(
    user_text: str,
    history: Optional[List[Dict[str, str]]] = None,
    mode: str = "practice",
) -> Dict[str, Any]:
    """Ask the LLM for a corrected sentence plus a spoken reply.

    Walks the configured LLM provider chain until one succeeds.
    """
    system_prompt = _build_system_prompt(mode, bool(history))

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]
    for entry in (history or [])[-6:]:
        role = entry.get("role")
        content = entry.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_text})

    chain = _split_chain(settings.LLM_PROVIDER_ORDER) or ["pollinations"]
    errors: List[str] = []

    for name in chain:
        provider = LLM_PROVIDERS.get(name)
        if provider is None:
            errors.append(f"{name}: unknown provider")
            continue
        try:
            content, model = await provider(messages)
        except ProviderError as exc:
            errors.append(f"{name}: {exc}")
            logger.warning("AI provider %s failed, trying the next one: %s", name, exc)
            continue
        except Exception as exc:  # network hiccup, bad JSON, anything else
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
            logger.warning(
                "AI provider %s raised %s, trying the next one: %s",
                name, type(exc).__name__, exc,
            )
            continue

        result = _parse_coach_json(content, user_text)
        result["model"] = model
        result["provider"] = name
        return result

    raise HTTPException(
        status_code=503,
        detail=(
            "No AI provider could answer. Tried: "
            + "; ".join(errors)
            + ". Check the provider settings in backend/.env."
        ),
    )


async def transcribe_audio(
    audio_bytes: bytes, filename: str = "speech.webm", content_type: str = "audio/webm"
) -> str:
    """Transcribe recorded speech to text.

    Walks the configured STT provider chain until one succeeds. When no
    server-side provider is configured the browser's own SpeechRecognition
    API is used instead - see the admin UI.
    """
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="No audio was received")

    chain = _split_chain(settings.STT_PROVIDER_ORDER)
    errors: List[str] = []

    for name in chain:
        provider = STT_PROVIDERS.get(name)
        if provider is None:
            errors.append(f"{name}: unknown provider")
            continue
        try:
            text = await provider(audio_bytes, filename, content_type)
        except ProviderError as exc:
            errors.append(f"{name}: {exc}")
            logger.warning("STT provider %s failed: %s", name, exc)
            continue
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
            logger.warning(
                "STT provider %s raised %s: %s", name, type(exc).__name__, exc
            )
            continue
        if text:
            return text
        errors.append(f"{name}: returned empty text")

    raise HTTPException(
        status_code=503,
        detail=(
            "No speech-to-text provider could transcribe the audio. Tried: "
            + "; ".join(errors)
            + ". The admin UI falls back to the browser's built-in "
            "speech recognition when no server-side provider is configured."
            + (
                " Add a free GROQ_API_KEY (console.groq.com/keys) for "
                "server-side Whisper transcription."
                if any("GROQ_API_KEY is not set" in e for e in errors)
                else ""
            )
        ),
    )


async def synthesize_speech(text: str, voice: str = "default") -> Tuple[bytes, str]:
    """Turn text into spoken audio.

    Returns (audio_bytes, media_type).
    """
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to speak")

    chain = _split_chain(settings.TTS_PROVIDER_ORDER) or ["edge"]
    errors: List[str] = []

    for name in chain:
        provider = TTS_PROVIDERS.get(name)
        if provider is None:
            errors.append(f"{name}: unknown provider")
            continue
        try:
            audio, media_type = await provider(text, voice)
        except ProviderError as exc:
            errors.append(f"{name}: {exc}")
            continue
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        if audio:
            return audio, media_type
        errors.append(f"{name}: returned no audio")

    raise HTTPException(
        status_code=503,
        detail=(
            "No text-to-speech provider could produce audio. Tried: "
            + "; ".join(errors)
            + ". The admin UI falls back to the browser's built-in "
            "speech synthesis when no server-side provider is available."
        ),
    )


def _provider_ready(name: str, stage: str = "llm") -> Tuple[bool, str]:
    """Is this provider usable right now, and if not, why not?"""
    if name == "pollinations":
        return True, "keyless"
    if name == "groq":
        if settings.GROQ_API_KEY:
            return True, settings.GROQ_LLM_MODEL
        return False, "GROQ_API_KEY is not set"
    if name == "nvidia":
        # NVIDIA is an LLM provider ONLY. It has no ASR or TTS model, so
        # advertising it as a ready STT/TTS provider sends a doomed request
        # and buries the real reason behind a confusing error.
        if stage != "llm":
            return False, "NVIDIA has no speech-to-text or speech-synthesis model"
        if settings.NVIDIA_API_KEY:
            return True, settings.NVIDIA_LLM_MODEL
        return False, "NVIDIA_API_KEY is not set"
    if name == "edge":
        if stage != "tts":
            return False, "Microsoft Edge TTS is a speech-synthesis provider only"
        try:
            import edge_tts  # noqa: F401
            return True, settings.EDGE_TTS_VOICE
        except ImportError:
            return False, "edge-tts is not installed"
    return False, "unknown provider"


def ai_status() -> Dict[str, Any]:
    """Report what the AI Agent can currently do - used by the UI to enable/disable controls."""
    groups = {
        "llm": _split_chain(settings.LLM_PROVIDER_ORDER),
        "stt": _split_chain(settings.STT_PROVIDER_ORDER),
        "tts": _split_chain(settings.TTS_PROVIDER_ORDER),
    }

    providers: Dict[str, List[Dict[str, Any]]] = {}
    for stage, chain in groups.items():
        entries = []
        for name in chain:
            ready, detail = _provider_ready(name, stage)
            entries.append({"name": name, "ready": ready, "detail": detail})
        providers[stage] = entries

    llm_ready = any(p["ready"] for p in providers["llm"])
    tts_ready = any(p["ready"] for p in providers["tts"])

    return {
        # True when the agent can hold a conversation and speak back.
        "configured": llm_ready and tts_ready,
        "providers": providers,
        # Browser-side fallbacks the UI should know about.
        "browser_fallback": {
            "speech_recognition": True,
            "speech_synthesis": True,
        },
        # Kept for backwards compatibility with the existing admin UI.
        "models": {
            "stt": settings.GROQ_STT_MODEL,
            "llm": settings.POLLINATIONS_MODEL,
            "tts": settings.EDGE_TTS_VOICE,
        },
        "base_url": settings.POLLINATIONS_BASE_URL,
    }
