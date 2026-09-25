import json
from pathlib import Path

import faiss


def export_faiss_json(index_path: Path, output_path: Path | None = None) -> Path:
    """Bir FAISS indeksini insan tarafından okunabilir JSON olarak dışa aktarır."""
    index = faiss.read_index(str(index_path))
    output_path = output_path or index_path.with_suffix(".json")
    vectors = [index.reconstruct(position).astype(float).tolist() for position in range(index.ntotal)]
    payload = {
        "faiss_file": index_path.name,
        "index_type": type(index).__name__,
        "metric": "inner_product_cosine_on_normalized_vectors",
        "vector_count": int(index.ntotal),
        "dimension": int(index.d),
        "vectors": [
            {"faiss_position": position, "embedding": vector}
            for position, vector in enumerate(vectors)
        ],
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path

