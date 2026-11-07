# Adding or improving a language

Two small JSON files per language. No code.

1. `config/includes.chroot/usr/share/saymy/i18n/<code>.json`: interface strings. Copy `en.json`,
   translate the values (never the keys), set `_meta.name` to the language's own name.
2. `config/includes.chroot/usr/share/saymy/say/intents/<code>.json`: the phrases people say.
   Each intent has a list of `patterns`. `{app}`, `{query}`, `{expr}` are slots for what follows.
   Add as many natural phrasings as people really use, including slang.

Missing keys fall back to English, so partial translations are safe. Run `bash tests/run-all.sh`
to confirm the files are valid.

Luganda (`lg`) is empty and waiting for a native speaker. Kiswahili (`sw`) is a draft awaiting review.

New locales for the OS itself (dates, numbers) are enabled in `config/hooks/live/0100-branding.hook.chroot`.
