"""Check the integration's request code against the real OpenRouter API.

Usage (from the repo root, mise activates the venv):

    OPENROUTER_API_KEY=sk-or-... python scripts/manual_test.py <input.wav> [out_dir]

Validates the key, lists the TTS voices, transcribes the input WAV, and writes
tts_sample.mp3 to the output directory (default: manual_test_output/, git-ignored).
"""

import asyncio
import os
from pathlib import Path
import sys

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.openrouter_speech.api import OpenRouterClient
from custom_components.openrouter_speech.const import (
    DEFAULT_BASE_URL,
    RECOMMENDED_STT_OPTIONS,
    RECOMMENDED_TTS_OPTIONS,
)

TEXT = "Bonjour ! J'ai allumé la lumière du salon et réglé le chauffage à vingt degrés."


async def main(input_wav: Path, out_dir: Path) -> None:
    """Run the checks."""
    stt_model = RECOMMENDED_STT_OPTIONS["model"]
    tts_model = RECOMMENDED_TTS_OPTIONS["model"]
    voice = RECOMMENDED_TTS_OPTIONS["voice"]
    out_dir.mkdir(parents=True, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        client = OpenRouterClient(
            session,
            os.environ["OPENROUTER_API_KEY"],
            os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL),
        )
        await client.async_validate_key()
        print("API key: OK")

        voices = await client.async_list_voices(tts_model)
        print(
            f"{tts_model}: {len(voices)} voices, french: {[v for v in voices if v.startswith('fr_')]}"
        )

        mp3 = await client.async_speak(tts_model, TEXT, voice, "mp3")
        (out_dir / "tts_sample.mp3").write_bytes(mp3)
        print(f"TTS: mp3 {len(mp3)} bytes (starts {mp3[:3]!r}) -> {out_dir}")

        text = await client.async_transcribe(stt_model, input_wav.read_bytes(), "fr")
        print(f"STT ({input_wav}): {text!r}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(
            "usage: OPENROUTER_API_KEY=sk-or-... "
            "python scripts/manual_test.py <input.wav> [out_dir]"
        )
    asyncio.run(
        main(
            Path(args[0]),
            Path(args[1]) if len(args) > 1 else Path("manual_test_output"),
        )
    )
