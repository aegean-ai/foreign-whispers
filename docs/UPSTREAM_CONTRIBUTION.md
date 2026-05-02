# Filing issues and opening pull requests (aegean-ai/foreign-whispers)

The course asks contributors to **file issues** and **submit pull requests** on the public repository:  
https://github.com/aegean-ai/foreign-whispers

## One-time setup

1. **Fork** the repository on GitHub (your account → Fork).
2. Add your fork as a remote (replace `YOURUSER`):

   ```bash
   git remote add fork git@github.com:YOURUSER/foreign-whispers.git
   ```

3. Keep `origin` as the upstream course repo, or rename remotes to taste:

   ```bash
   git remote rename origin upstream
   git remote add origin git@github.com:YOURUSER/foreign-whispers.git
   ```

## Suggested GitHub issues (copy into GitHub → Issues → New)

You can open these as **separate issues** and then reference them in your PR (`Fixes #NNN`).

Paste-ready bodies live in this repo:

| Topic | File to copy from |
|-------|-------------------|
| Remote GPU + SSH tunnel docs | [`docs/github-issue-remote-gpu.md`](./github-issue-remote-gpu.md) |
| TTS `speaker_wav` / `resolve_speaker_wav` parity | [`docs/github-issue-tts-speaker-wav.md`](./github-issue-tts-speaker-wav.md) |

Suggested **titles**:

1. `docs: CPU orchestrator + remote Speaches/Chatterbox (lab cluster)`
2. `feat(api): optional speaker_wav query + resolve_speaker_wav wiring for TTS`

## Opening the PR

1. Create a branch from an up-to-date `main`:

   ```bash
   git fetch upstream
   git checkout -b feat/course-remote-gpu-docs upstream/main
   # or: git checkout -b feat/your-topic main
   ```

2. Cherry-pick or copy your commits, then:

   ```bash
   git push -u origin feat/course-remote-gpu-docs
   ```

3. On GitHub: **Compare & pull request** from `YOURUSER:feat/course-remote-gpu-docs` → `aegean-ai:main`.

4. In the PR description, link the issues (`Closes #123` or `See #124`), summarize changes, and note anything that intentionally diverges from the assignment handout (see main **README.md** section “Implementation notes”).

## If `gh` CLI is installed

```bash
gh issue create --repo aegean-ai/foreign-whispers --title "..." --body-file docs/github-issue-remote-gpu.md
gh pr create --repo aegean-ai/foreign-whispers --base main --head YOURUSER:feat/branch --fill
```

You still need push access to **your fork**; you do **not** need push access to `aegean-ai` directly.
