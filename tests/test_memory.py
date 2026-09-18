import uuid

from langgraph.checkpoint.memory import MemorySaver

from app.memory.cross_thread_memory import CrossThreadMemoryManager
from app.memory.database_memory import PersistentDatabaseMemoryManager
from app.memory.episodic_memory import EpisodicMemoryManager
from app.memory.factory import MemoryFactory
from app.memory.langchain_memory import LangChainMemoryManager
from app.memory.langgraph_memory import LangGraphMemoryManager
from app.memory.long_term_memory import LongTermMemoryManager
from app.memory.no_memory import NoMemoryManager
from app.memory.procedural_memory import ProceduralMemoryManager
from app.memory.semantic_memory import SemanticMemoryManager


def make(mode: str, **kwargs):
    return MemoryFactory.create(
        mode,
        tenant_id=kwargs.pop("tenant_id", "tenant-a"),
        user_id=kwargs.pop("user_id", "user-a"),
        conversation_id=kwargs.pop("conversation_id", "conversation-a"),
        **kwargs,
    )


def test_no_memory_does_not_retain_turns() -> None:
    manager = make("none")
    assert isinstance(manager, NoMemoryManager)
    manager.save_turn("remember me", "I will not retain this")

    assert manager.load_context() == []
    assert manager.get_history() == []


def test_short_term_memory_stores_and_retrieves_turns() -> None:
    manager = make("short_term")
    assert isinstance(manager, LangChainMemoryManager)
    manager.save_turn("What is LangChain?", "LangChain is an enterprise AI framework.")

    context = manager.load_context()
    assert len(context) == 2
    assert context[0]["role"] == "user"
    assert context[0]["content"] == "What is LangChain?"
    assert context[1]["role"] == "assistant"
    assert context[1]["content"] == "LangChain is an enterprise AI framework."


def test_langchain_memory_sliding_window_pruning() -> None:
    manager = make("langchain", window_size=1)
    manager.save_turn("turn 1 question", "turn 1 answer")
    manager.save_turn("turn 2 question", "turn 2 answer")

    context = manager.load_context()
    assert len(context) == 2
    assert context[0]["content"] == "turn 2 question"
    assert context[1]["content"] == "turn 2 answer"


def test_langchain_memory_clear_wipes_history() -> None:
    manager = make("langchain", conversation_id=f"langchain-clear-{uuid.uuid4()}")
    manager.save_turn("Hello", "Hi there")
    assert len(manager.load_context()) == 2

    manager.clear()
    assert len(manager.load_context()) == 0


def test_checkpoint_memory_persists_checkpoints() -> None:
    saver = MemorySaver()
    first = make("checkpoint", checkpointer=saver)
    assert isinstance(first, LangGraphMemoryManager)
    first.save_turn("Step 1 query", "Step 1 response")

    # Second manager instance on the same checkpointer recovers state
    second = make("checkpoint", checkpointer=saver)
    context = second.load_context()
    assert len(context) == 2
    assert context[0]["content"] == "Step 1 query"
    assert context[1]["content"] == "Step 1 response"


def test_checkpoint_memory_scoped_by_conversation() -> None:
    saver = MemorySaver()
    conv1 = make("checkpoint", checkpointer=saver, conversation_id="conv-1")
    conv2 = make("checkpoint", checkpointer=saver, conversation_id="conv-2")

    conv1.save_turn("Secret A", "Response A")
    assert len(conv1.load_context()) == 2
    assert len(conv2.load_context()) == 0


def test_checkpoint_memory_clear() -> None:
    saver = MemorySaver()
    manager = make("checkpoint", checkpointer=saver)
    manager.save_turn("Query", "Answer")
    assert len(manager.load_context()) == 2

    manager.clear()
    assert len(manager.load_context()) == 0


def test_long_term_memory_user_scoped_across_conversations() -> None:
    conv1 = make("long_term", user_id="user-1", conversation_id="conv-1")
    conv2 = make("long_term", user_id="user-1", conversation_id="conv-2")
    diff_user = make("long_term", user_id="user-2", conversation_id="conv-3")

    assert isinstance(conv1, LongTermMemoryManager)
    conv1.save_turn("My favorite framework is LangChain", "Noted for your profile.")

    # Context in conv2 under same user retrieves the user profile context
    context2 = conv2.load_context()
    assert len(context2) >= 1
    assert any("LangChain" in c["content"] for c in context2)

    # Different user has empty context
    assert len(diff_user.load_context()) == 0


def test_long_term_memory_remembers_user_name_across_conversations() -> None:
    conv1 = make("long_term", user_id="user-name", conversation_id="conv-name-1")
    conv2 = make("long_term", user_id="user-name", conversation_id="conv-name-2")

    conv1.save_turn("My name is Alice Johnson", "Nice to meet you, Alice!")

    profile = conv2.get_user_profile()
    assert profile["name"] == "Alice Johnson"
    context = conv2.load_context()
    assert any("Alice Johnson" in c["content"] for c in context)


def test_long_term_memory_extracts_name_before_extra_sentence_clauses() -> None:
    conv1 = make("long_term", user_id="user-name-2", conversation_id="conv-name-3")

    conv1.save_turn("My name is yash and I work in eidiko", "Nice to meet you!")

    profile = conv1.get_user_profile()
    assert profile["name"] == "yash"


def test_cross_thread_memory_tenant_scoped() -> None:
    thread1 = make("cross_thread", tenant_id="tenant-1", conversation_id="thread-1")
    thread2 = make("cross_thread", tenant_id="tenant-1", conversation_id="thread-2")
    diff_tenant = make("cross_thread", tenant_id="tenant-2", conversation_id="thread-3")

    assert isinstance(thread1, CrossThreadMemoryManager)
    thread1.save_turn("Company server is server.corp.internal", "Recorded shared infrastructure.")

    # Thread 2 in same tenant gets shared tenant knowledge
    context = thread2.load_context()
    assert len(context) >= 1
    assert any("server.corp.internal" in c["content"] for c in context)

    # Different tenant has zero cross-thread context
    assert len(diff_tenant.load_context()) == 0


def test_semantic_memory_turn_search() -> None:
    manager = make("semantic")
    assert isinstance(manager, SemanticMemoryManager)
    manager.save_turn("How do we deploy to AWS EKS?", "Use the Terraform scripts in /infra.")
    manager.save_turn("What is our cafeteria menu?", "Pizza on Fridays.")

    # Load context should retrieve both turn messages and semantic matches
    context = manager.load_context(query="AWS deployment")
    assert len(context) >= 2
    contents = [c["content"] for c in context]
    assert any("Terraform" in c for c in contents)


def test_semantic_memory_handles_short_embedding_results() -> None:
    class ShortEmbeddingProvider:
        def embed_documents(self, texts):
            return [[0.1, 0.2, 0.3]]

        def embed_query(self, text):
            return [0.1, 0.2, 0.3]

    manager = make("semantic", embeddings=ShortEmbeddingProvider())
    manager.save_turn("Deploy to EKS", "Use the Terraform scripts in /infra.")

    context = manager.load_context(query="AWS deployment")
    assert len(context) >= 1
    contents = [c["content"] for c in context]
    assert any("Deploy to EKS" in c or "Terraform" in c for c in contents)


def test_episodic_memory_structured_episodes() -> None:
    manager = make("episodic")
    assert isinstance(manager, EpisodicMemoryManager)
    manager.save_episode(
        situation="Database high CPU alert",
        action="Indexed queries on memory_id",
        outcome="Latency reduced from 450ms to 20ms",
        metadata={"service": "postgres"},
    )

    episodes = manager.get_episodes()
    assert len(episodes) == 1
    assert episodes[0]["situation"] == "Database high CPU alert"

    context = manager.load_context()
    assert len(context) >= 1
    assert "Database high CPU alert" in context[0]["content"]


def test_procedural_memory_guidelines_and_rules() -> None:
    manager = make("procedural")
    assert isinstance(manager, ProceduralMemoryManager)
    manager.add_procedure(
        "SOC2_Compliance",
        "Never log raw customer tokens or credentials.",
    )

    context = manager.load_context()
    assert len(context) >= 1
    assert any("SOC2_Compliance" in c["content"] for c in context)


def test_persistent_database_memory() -> None:
    manager = make("persistent_db")
    assert isinstance(manager, PersistentDatabaseMemoryManager)
    manager.save_turn("Database test prompt", "Database test reply")

    context = manager.load_context()
    assert len(context) == 2
    assert context[0]["content"] == "Database test prompt"
    assert context[1]["content"] == "Database test reply"


def test_legacy_aliases_route_correctly() -> None:
    for alias in ("buffer", "window", "summary"):
        manager = make(alias)
        assert isinstance(manager, LangChainMemoryManager)

    db_manager = make("persistent")
    assert isinstance(db_manager, PersistentDatabaseMemoryManager)
