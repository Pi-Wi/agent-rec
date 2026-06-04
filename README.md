# agentrec

Framework-agnostic record/replay for streaming LLM API interactions.
Records and replays at the **httpx transport layer**, so it works below
OpenAI SDK, Anthropic SDK, LangChain, or any other httpx-backed client.

> **Status:** streaming prototype — proves the core mechanic.

---

## Architecture

```
agentrec/
  capture.py    # CapturedChunk, CapturedInteraction — storage-agnostic data
  store.py      # InteractionStore ABC + InMemoryStore
  transport.py  # RecordingTransport, ReplayTransport (_TeeStream, _ReplayStream)
```

Key design commitments visible in this prototype:

- **Tee, don't intercept-and-buffer.** `RecordingTransport` wraps the live
  stream so the caller and the store both see every chunk in order, without
  the recorder buffering the whole response first.
- **Raw bytes, no parsing.** Chunks are stored as the original SSE byte frames.
  The SDK parser re-runs on replay and produces the same objects it would have
  from the network.
- **Injected store.** `InMemoryStore` is the first implementation of
  `InteractionStore`.  Future implementations (YAML cassette, Parquet corpus)
  drop in without touching transport code.
- **Distinct transport classes.** `RecordingTransport` requires an inner
  transport; `ReplayTransport` has none — it cannot accidentally touch the
  network.

---

## Running the tests

### Install

```bash
pip install -e ".[dev]"
```

### Offline replay test (no API key needed)

Proves the replay mechanic with hardcoded SSE frames:

```bash
pytest tests/test_streaming.py::test_replay_offline -v
```

### Live record → replay test (requires OpenAI API key)

Records a real streaming tool-call response, then replays it offline and
asserts the assembled message is identical:

```bash
export OPENAI_API_KEY=sk-...
pytest tests/test_streaming.py::test_record_and_replay -v
```

The replay phase patches `httpx.AsyncHTTPTransport.handle_async_request` to
raise immediately, so any accidental real-network access will fail the test.

---

## Quick usage sketch

```python
import httpx
from openai import AsyncOpenAI
from agentrec import InMemoryStore, RecordingTransport, ReplayTransport

store = InMemoryStore()
iid = "my_interaction"

# --- Record (needs network) ---
async with httpx.AsyncClient(
    transport=RecordingTransport(httpx.AsyncHTTPTransport(), store, iid)
) as http_client:
    client = AsyncOpenAI(http_client=http_client)
    stream = await client.chat.completions.create(..., stream=True)
    async for chunk in stream:
        ...   # caller receives live stream unchanged

# --- Replay (offline) ---
async with httpx.AsyncClient(transport=ReplayTransport(store, iid)) as http_client:
    client = AsyncOpenAI(http_client=http_client)
    stream = await client.chat.completions.create(..., stream=True)
    async for chunk in stream:
        ...   # identical to the recorded run
```

---

## Attributions

See [NOTICE](NOTICE) for third-party acknowledgements, including inspiration
from **baml_vcr** for the streaming chunk capture/replay pattern.
