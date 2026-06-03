"""Build and store review embeddings."""

from typing import Iterable, List, Sequence

from openai import OpenAI

EMBEDDING_DIMENSIONS = 1536


def build_review_text(product_name: str, review: dict) -> str:
    return (
        f"Product: {product_name}. "
        f"Rating: {review.get('rating', '')}/5. "
        f"Review: {review.get('review', '')}. "
        f"Pros: {review.get('reviewPros', '')}. "
        f"Cons: {review.get('reviewCons', '')}. "
        f"Sentiment: {review.get('emotion', '')}. "
        f"Author job title: {review.get('reviewAuthorJobTitle', '')}. "
        f"Date: {review.get('reviewDate', '')}."
    )


def build_search_text(review: dict) -> str:
    return " ".join(
        filter(
            None,
            [
                review.get("review", ""),
                review.get("reviewPros", ""),
                review.get("reviewCons", ""),
                review.get("emotion", ""),
                review.get("reviewAuthorJobTitle", ""),
                review.get("reviewDate", ""),
            ],
        )
    )


def embed_texts(client: OpenAI, texts: Sequence[str], model: str) -> List[List[float]]:
    if not texts:
        return []
    response = client.embeddings.create(model=model, input=list(texts))
    return [item.embedding for item in response.data]


def embed_reviews(
    client: OpenAI,
    product_name: str,
    reviews: Iterable[dict],
    model: str,
) -> List[tuple[dict, List[float], str]]:
    review_list = list(reviews)
    if not review_list:
        return []

    texts = [build_review_text(product_name, review) for review in review_list]
    vectors = embed_texts(client, texts, model)
    return [
        (review, vector, build_search_text(review))
        for review, vector in zip(review_list, vectors)
    ]
