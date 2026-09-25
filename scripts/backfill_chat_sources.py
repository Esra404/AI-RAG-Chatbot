from app.config import CONFIG_DIR
from app.rag import retrieve
from app.storage import JsonStore


def main() -> None:
    chats_store = JsonStore(CONFIG_DIR / "chats.json", {"chats": []})
    documents_store = JsonStore(CONFIG_DIR / "document_registry.json", {"documents": []})
    documents = documents_store.read()["documents"]
    updated = 0

    def migrate(data):
        nonlocal updated
        for chat in data["chats"]:
            last_question = ""
            for message in chat.get("messages", []):
                if message.get("role") == "user":
                    last_question = message.get("content", "")
                    continue
                sources = message.get("sources", [])
                if message.get("role") != "assistant" or not sources or all(source.get("chunk") for source in sources):
                    continue
                fresh_sources = retrieve(last_question, documents, top_k=len(sources))
                if not fresh_sources:
                    continue
                message["sources"] = [
                    {
                        "number": position,
                        "document_id": source["document_id"],
                        "document_name": source["document_name"],
                        "chunk_position": source["chunk_position"],
                        "chunk": source["chunk"],
                        "score": round(source["score"], 4),
                    }
                    for position, source in enumerate(fresh_sources, 1)
                ]
                updated += 1

    chats_store.update(migrate)
    print(f"BACKFILLED_MESSAGES={updated}")


if __name__ == "__main__":
    main()

