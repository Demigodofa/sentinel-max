from sentinel.memory.intelligence import MemoryContextBuilder, MemoryFilter, MemoryRanker
from sentinel.memory.memory_manager import MemoryManager


def test_memory_context_builder_filters_duplicates(tmp_path):
    memory = MemoryManager(storage_dir=tmp_path)
    memory.store_text("primary fact", namespace="notes", metadata={"tags": ["code"]})
    memory.store_text("primary fact", namespace="notes", metadata={"tags": ["code"]})
    memory.store_text("short", namespace="notes", metadata={"tags": ["code"]})

    ranker = MemoryRanker(memory)
    builder = MemoryContextBuilder(memory, ranker=ranker, mem_filter=MemoryFilter(min_length=5))
    memories, context_block = builder.build_context("write code", "code_generation", limit=3)

    primary = [m for m in memories if m.get("text") == "primary fact"]
    assert len(primary) == 1
    assert "primary fact" in context_block
