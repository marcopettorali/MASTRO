# Vosk model for `audio_transcription`

`audio_transcription` runs speech-to-text with [Vosk](https://alphacephei.com/vosk/) when the
`vosk` Python package is installed on the node and a model is present in this folder (override
with the `VOSK_MODEL_PATH` environment variable).

**Model used in the experiments:** <MODEL_NAME> — <MODEL_LINK>

Vosk toolkit: https://github.com/alphacep/vosk-api — all models: https://alphacephei.com/vosk/models.
The pipeline works on 16 kHz mono audio, so use an English model for 16 kHz input.

Extract the model so that its files (`am/`, `conf/`, `graph/`, ...) are directly in this folder,
and install the package on the node:

```bash
pip install vosk
```

Without the package or the model the service falls back to a deterministic analysis that does
not perform real speech recognition and returns the phrase carried in the request payload.
