"""
Confidence scoring for RAG results.
Determines whether to return results or escalate to a human.
"""

import os

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.65"))


def assess_confidence(results: list) -> dict:
    """
    Assess whether the retrieval results are confident enough to return.

    Returns:
        {
            "confident": bool,
            "top_score": float,
            "avg_score": float,
            "result_count": int,
            "recommendation": "return" | "escalate"
        }
    """
    if not results:
        return {
            "confident": False,
            "top_score": 0.0,
            "avg_score": 0.0,
            "result_count": 0,
            "recommendation": "escalate",
        }

    scores = [r.relevance_score for r in results if hasattr(r, 'relevance_score')]
    top_score = max(scores)
    avg_score = sum(scores) / len(scores)

    confident = top_score >= CONFIDENCE_THRESHOLD

    return {
        "confident": confident,
        "top_score": round(top_score, 4),
        "avg_score": round(avg_score, 4),
        "result_count": len(results),
        "recommendation": "return" if confident else "escalate",
    }
