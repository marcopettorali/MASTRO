# Audio dataset for `tg_audio`

`tg_audio` reads the `.wav` files in this folder (override with the `TG_WAV_PATH` environment
variable) and sends them, one per request and in sorted order, to the voice pipeline.

**Source:** Google Speech Commands v0.02 — http://download.tensorflow.org/data/speech_commands_v0.02.tar.gz

P. Warden, *Speech Commands: A Dataset for Limited-Vocabulary Speech Recognition*,
arXiv:1804.03209, 2018. Released under the CC BY 4.0 license.

Expected content:
- one WAV clip per request (mono, 16 kHz, 16-bit PCM);
- **the file name is the spoken command**, with words separated by `_` or `-`
  (e.g. `turn_on.wav`): the generator sends it along with the audio as the reference phrase of
  the request.

The repository includes four sample clips taken from the dataset (`yes.wav`, `no.wav`, `go.wav`,
`down.wav`), enough to run the pipeline end to end. To use more clips, extract the archive and copy
them into this folder, renaming them after the word they contain (in the archive, each word has
its own folder).
