"""ChromaDB vector store for semantic search over products and guides."""

import os
import chromadb

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma")

_store = None


def get_vector_store():
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_DIR)
        self.products = self.client.get_or_create_collection("products")
        self.guides = self.client.get_or_create_collection("guides")

    def add_product(self, product: dict):
        ps = product.get("ps_number", "")
        if not ps:
            return
        doc = " | ".join(filter(None, [
            product.get("name", ""),
            product.get("description", ""),
            product.get("category", ""),
            product.get("subcategory", ""),
            product.get("brand", ""),
            " ".join(product.get("symptoms", [])),
        ]))
        self.products.upsert(
            ids=[ps],
            documents=[doc],
            metadatas=[{
                "ps_number": ps,
                "name": product.get("name", ""),
                "price": float(product.get("price", 0)),
                "category": product.get("category", ""),
                "brand": product.get("brand", ""),
                "in_stock": product.get("in_stock", True),
                "rating": float(product.get("rating", 0)),
            }],
        )

    def add_guide(self, guide: dict):
        key = guide.get("problem_key", "")
        if not key:
            return
        doc = " | ".join(filter(None, [
            guide.get("title", ""),
            " ".join(guide.get("symptoms", [])),
            " ".join(guide.get("diagnosis_steps", [])),
        ]))
        self.guides.upsert(
            ids=[key],
            documents=[doc],
            metadatas=[{
                "category": guide.get("category", ""),
                "title": guide.get("title", ""),
                "problem_key": key,
            }],
        )

    def search_products(self, query: str, category: str = None, n_results: int = 10) -> list[dict]:
        kwargs = {"query_texts": [query], "n_results": n_results}
        if category:
            kwargs["where"] = {"category": category}
        try:
            results = self.products.query(**kwargs)
        except Exception:
            results = self.products.query(query_texts=[query], n_results=n_results)

        out = []
        if results and results.get("ids") and results["ids"][0]:
            for i, pid in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                dist = results["distances"][0][i] if results.get("distances") else 0
                out.append({"ps_number": pid, "score": 1 - dist, **meta})
        return out

    def search_guides(self, query: str, category: str = None, n_results: int = 3) -> list[dict]:
        kwargs = {"query_texts": [query], "n_results": n_results}
        if category:
            kwargs["where"] = {"category": category}
        try:
            results = self.guides.query(**kwargs)
        except Exception:
            results = self.guides.query(query_texts=[query], n_results=n_results)

        out = []
        if results and results.get("ids") and results["ids"][0]:
            for i, gid in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                out.append({"problem_key": gid, **meta})
        return out

    def get_stats(self) -> dict:
        return {
            "products": self.products.count(),
            "guides": self.guides.count(),
        }
