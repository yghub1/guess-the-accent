# Guess the Accent

A listening game. You hear one sentence spoken by a voice from somewhere in the
world, and you pick which accent it was. Ten clips a round, solo or two players
taking turns.

- **English accents** — British, Irish, Kiwi, Nigerian, Singaporean, Sri Lankan
  and more.
- **World tour** — the same game with languages instead of English accents.
- **Easy** spreads the wrong answers across the map; **Tricky** serves you the
  neighbours, so Australian sits next to New Zealander and Spain next to
  Argentina.
- Replay, *Slow it down*, *Show the words*, keyboard 1–4, and a one-line fact
  after each answer about what gives that accent away.

## Playing it

Open `index.html` in a browser. That is the whole game — one file, no build
step, no server, no dependencies.

To put it online, push to GitHub and turn on Pages (Settings → Pages → Source:
GitHub Actions). The included workflow publishes the repo root on every push to
`main`; there is nothing to build.

## How the audio works

There are no recordings in this repo. The game asks the browser's built-in
speech engine (the Web Speech API) for a voice tagged with a given locale —
`en-IE`, `en-NZ`, `fr-CA`, `ja-JP` and so on — and has it read a short sentence.
Nothing is recorded and no audio leaves the device.

The practical consequence: **the roster of accents depends on the device.**
Chrome and Edge on a computer stream a wide set of voices while online; Android
and iOS use whatever speech languages are installed. The start screen counts
what it found and needs at least four to deal a round. If a device is short on
voices, the start screen explains where to add more.

English sentences are picked to make accents give themselves away — r-dropping
("park the car"), the vowel in *dance*, the *i* in *fish*, the *t* in *butter*.

## Editing it

Everything lives in `index.html`:

- `ACCENTS` — the catalogue. Each entry is a BCP-47 `tag` the speech engine is
  asked for, plus the flag, display name, a `cluster`, and the fact shown after
  the answer. `cluster` is what makes Tricky mode hard: wrong answers are drawn
  from the same cluster, so Australian shows up next to New Zealander.
- `EN_PHRASES` — the English sentence pool.
- `WORLD_PHRASES` — one line per language for the World tour pack, keyed by
  language code, with `PHRASE_OVERRIDES` for scripts that differ by region.
- `normalizeTag` — some engines report `eng-GBR` instead of `en-GB`; this maps
  the three-letter codes back so those voices are still found.

Adding an accent is one entry in `ACCENTS` (plus a phrase, for a new language).
It only appears in the game on devices that actually have a matching voice.

### Swapping in real recordings

If you ever want real human voices instead of synthesised ones, the only piece
that has to change is `speak()` — play an `<audio>` element instead of an
utterance, and give each `ACCENTS` entry a clip list. Everything else (rounds,
scoring, distractors, two-player turns) is independent of where the sound comes
from. Note that real recordings need clearing for licensing first; that is why
this version uses the voices already on the device.

## Chatterbox voices (pre-recorded)

The start screen has a **Voices** switch: *This device* uses the speech engine
as described above; *Chatterbox* plays clips rendered ahead of time with
[Chatterbox](https://github.com/resemble-ai/chatterbox) (MIT), an open-source
model that copies a voice — and its accent — from a ten-second sample. Those
clips live in `audio/chatterbox/` and are listed in
`audio/chatterbox/manifest.js`, so they sound the same on every device.

The samples are real speakers from two open corpora by CSTR, University of
Edinburgh: **VCTK** (CC BY 4.0) and **EdAcc** (CC BY-SA 4.0). Per-file credits
are in `tools/voicegen/refs/CREDITS.txt`.

To regenerate or extend them (Apple Silicon or any machine with Python 3.11):

```
cd tools/voicegen
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python chatterbox-tts huggingface_hub "pyarrow<17" soundfile "setuptools<81"
.venv/bin/python fetch_refs.py            # reference samples → refs/
.venv/bin/python generate.py              # every phrase, every voice (skips clips that exist)
.venv/bin/python generate.py --phrases 4 --only en-IE,en-NZ   # a quick subset
```

Accents with no reference sample yet (Pakistani, Sri Lankan, Singaporean,
Filipino, Hong Kong, Malaysian, and the World tour) are left out of the
Chatterbox roster; add a `refs/<tag>-<n>.wav` and run `generate.py` to include
one.
