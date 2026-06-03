"""Tests for Path A crawl logic."""

from src.crawl.jobs import reviews_until_duplicate
from src.extractor.hash import hash_review
from src.extractor.urls import build_reviews_page_url, normalize_capterra_url


def test_normalize_capterra_url():
    expected = "https://www.capterra.com/p/121248/When-I-Work/reviews/"
    assert normalize_capterra_url(expected) == expected
    assert (
        normalize_capterra_url("https://www.capterra.com/p/121248/When-I-Work/")
        == expected
    )
    assert (
        normalize_capterra_url("https://www.capterra.com/p/121248/When-I-Work/reviews/?page=3")
        == expected
    )


def test_build_reviews_page_url():
    base = "https://www.capterra.com/p/121248/When-I-Work/reviews/"
    assert build_reviews_page_url(base, 1) == base
    assert build_reviews_page_url(base, 2) == base + "?page=2"


def test_hash_review_stable():
    review = {
        "reviewDate": "2024-01-15",
        "reviewPros": "Good app",
        "reviewCons": "Pricey",
        "rating": "4",
    }
    assert hash_review(review) == hash_review(review)


def test_reviews_until_duplicate_stops_at_first_match():
    existing_review = {"reviewDate": "2024-01-01", "reviewPros": "a", "reviewCons": "b", "rating": "5"}
    existing = {hash_review(existing_review)}
    reviews = [
        {"reviewDate": "2024-02-01", "reviewPros": "new", "reviewCons": "", "rating": "5"},
        existing_review,
        {"reviewDate": "2023-01-01", "reviewPros": "old", "reviewCons": "", "rating": "3"},
    ]
    new_reviews, hit = reviews_until_duplicate(reviews, existing)
    assert hit is True
    assert len(new_reviews) == 1
    assert new_reviews[0]["reviewPros"] == "new"


def test_reviews_until_duplicate_all_new():
    reviews = [{"reviewDate": "2024-02-01", "reviewPros": "new", "reviewCons": "", "rating": "5"}]
    new_reviews, hit = reviews_until_duplicate(reviews, set())
    assert hit is False
    assert len(new_reviews) == 1

