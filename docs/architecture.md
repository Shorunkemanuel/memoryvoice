# MemoryVoice Architecture

## Core flow

Browser voice recording
→ FastAPI API
→ speech-to-text
→ Backboard Unified API
→ open model
→ structured memory
→ Backboard persistent memory/retrieval
→ MemoryVoice UI

## Responsibilities

### Frontend

React + Vite + TypeScript provides recording/upload UI, processing state, memory cards, memory detail, and retrieval.

### Backend

FastAPI provides audio processing, transcription, Backboard integration, memory operations, and SQLite metadata.

Secrets remain server-side.

### Backboard

Backboard is a core application dependency. It provides assistant/thread context, persistent memory, retrieval, and model access/routing.

An open model must be used for the core AI behavior to satisfy the hackathon's open-source-AI requirement.

### Render

Render hosts the deployed application/runtime and provides the public demo environment.

## MVP constraint

No authentication, payments, social features, mobile app, or multi-user collaboration in the hackathon MVP.
