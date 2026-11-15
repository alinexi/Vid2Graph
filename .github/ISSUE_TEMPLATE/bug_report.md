---
name: Bug report
about: Something broke while building, viewing, or exporting a graph
title: "[Bug] "
labels: bug
---

## What happened?

A clear description of the problem.

## How to reproduce

1. Source: YouTube URL / audio file / subtitle file
2. Steps in the UI or the `curl` command you ran
3. What you expected vs. what you saw

## Environment

- Vid2Graph version / commit:
- OS and install method (Docker / local):
- LLM provider and model (e.g. `ollama` + `qwen2.5:7b`):
- Whisper backend (if transcription ran):

## Logs

Paste the job log from the progress panel or `GET /api/jobs/{id}`, and any backend traceback.

```
<logs>
```
