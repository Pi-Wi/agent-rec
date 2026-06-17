"""
Store-interface contract tests (the base ABC + InMemoryStore).

FileStore's on-disk persistence is covered in test_filestore.py; these pin the
*enumeration* contract every store must satisfy to be migrated or annotated:
``ids()`` is sorted and synchronous, ``len()`` counts, and a store that does
not implement ``ids()`` fails with a clear NotImplementedError (naming the
method) rather than an AttributeError when the corpus tooling enumerates it.
"""
from __future__ import annotations

import pytest

from agentrec import InMemoryStore
from agentrec.capture import CapturedChunk, CapturedInteraction, CapturedRequest
from agentrec.store import InteractionStore


def _interaction(text: str = "hi") -> CapturedInteraction:
    return CapturedInteraction(
        request=CapturedRequest(method="POST", url="https://x/v1", headers=[], content=b"{}"),
        response_status=200,
        response_headers=[],
        response_extensions={},
        chunks=[CapturedChunk(data=text.encode())],
        metadata={},
    )


async def test_inmemory_ids_sorted_and_len_track_contents():
    store = InMemoryStore()
    assert store.ids() == [] and len(store) == 0
    await store.save("b", _interaction())
    await store.save("a", _interaction())
    assert store.ids() == ["a", "b"]  # sorted, matching FileStore's contract
    assert len(store) == 2
    await store.discard("a")
    assert store.ids() == ["b"] and len(store) == 1


def test_base_store_enumeration_raises_clear_error():
    """A store that doesn't implement ids() should fail with a NotImplementedError
    that names the method, not an AttributeError — so a custom store knows what
    it must add to be migratable. ``len()`` (which defaults to len(ids())) too."""
    class _Bare(InteractionStore):
        pass

    bare = _Bare()
    with pytest.raises(NotImplementedError, match="ids"):
        bare.ids()
    with pytest.raises(NotImplementedError):
        len(bare)
