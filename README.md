# OpenRouter Speech for Home Assistant

Speech-to-text and text-to-speech entities backed by
[OpenRouter's audio APIs](https://openrouter.ai/docs/api/api-reference/stt/create-transcription),
selectable in an Assist pipeline. Defaults to Mistral Voxtral
(`mistralai/voxtral-mini-transcribe-3-0` and `mistralai/voxtral-mini-tts-3-0`,
with the `fr_marie_neutral` voice on French installs and the model's own default
voice otherwise), but any OpenRouter transcription or speech model ID works.

This is not a conversation agent: use the built-in **OpenRouter** integration for
that. The domain is `openrouter_speech`, so both coexist.

Text-to-speech support is being added to the built-in integration
([home-assistant/core#184941](https://github.com/home-assistant/core/pull/184941)).
Once it ships, prefer it for TTS.

Requires Home Assistant 2026.10 or newer. No extra Python packages. The only
network traffic is HTTPS to OpenRouter.

## Install

**HACS:** HACS → ⋮ → *Custom repositories* → add this repository's URL as type
*Integration* → install **OpenRouter Speech** → restart Home Assistant.

**Manual:** copy `custom_components/openrouter_speech` into your
`<config>/custom_components/` folder and restart Home Assistant.

## Configure

1. *Settings → Devices & services → Add integration → OpenRouter Speech*.
2. Paste an API key from <https://openrouter.ai/settings/keys>. The key is checked
   with a free call. Leave the base URL alone unless you use another OpenRouter
   region (for example `https://eu.openrouter.ai/api/v1`, which needs a Business
   plan).
3. An **OpenRouter STT** and an **OpenRouter TTS** service are created. Click
   ⚙ on one of them to change it later, or *Add speech-to-text service* /
   *Add text-to-speech service* to add more (for example one per voice):
   - **STT:** model, and language: *use the pipeline language* (sent to the
     model as an ISO-639-1 hint, e.g. `fr-FR` → `fr`) or *auto-detect*.
   - **TTS:** model and default voice (dropdown filled from OpenRouter's model
     catalog; free text allowed). Changing to a model with no published voices
     clears the old voice unless you type a new one.

The key and base URL can be changed with *Reconfigure* on the integration entry.

## Use it in Assist

*Settings → Voice assistants →* pick or create an assistant → set
**Speech-to-text** to `OpenRouter STT` and **Text-to-speech** to `OpenRouter TTS`.

## tts.speak example

```yaml
action: tts.speak
target:
  entity_id: tts.openrouter_tts
data:
  media_player_entity_id: media_player.kitchen
  message: "Le linge est prêt."
  options:
    voice: fr_marie_happy   # overrides the default voice for this call
```

## Known limitations

- TTS always requests MP3. When a voice satellite wants WAV, Home Assistant
  converts it with ffmpeg.
- No streaming TTS: OpenRouter needs the whole text in one request.
- The voice list is fetched in the background when the integration loads (and
  again when you open a TTS service's settings if that failed). It isn't
  filtered by language. Voxtral names hint at the language (`fr_`, `en_`, `gb_`),
  but most of its voices are `voice_NNNN`.
- The supported-language list is fixed and the same for every model.
  Home Assistant needs it to offer the entity in a pipeline. The model decides
  what it can actually handle.
- No STT prompt or keyterms: OpenRouter only accepts keyterms for some providers.

## Development

```bash
mise install && mise run install
mise run test
mise run lint
```

Check against the real API (uses the integration's own request code):

```bash
OPENROUTER_API_KEY=sk-or-... python scripts/manual_test.py your_audio.wav
```

It validates the key, lists the voices, transcribes the WAV, and writes
`manual_test_output/tts_sample.mp3` (git-ignored).
