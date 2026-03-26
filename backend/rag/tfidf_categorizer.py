"""TF-IDF based paper categorization utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib


class TfidfPaperCategorizer:
    """Load trained TF-IDF artifacts and run single-example inference."""

    def __init__(self, model_dir: Path | None = None) -> None:
        self.model_dir = model_dir or self.default_model_dir()
        self.vectorizer = self._load_artifact("tfidf_vectorizer.joblib")
        self.model = self._load_artifact("tfidf_logreg.joblib")
        self.label_encoder = self._load_artifact("label_encoder.joblib")

    @staticmethod
    def default_model_dir() -> Path:
        """Return the default TF-IDF artifact directory for the project."""
        return Path(__file__).resolve().parents[2] / "models" / "tfidf"

    def _load_artifact(self, artifact_name: str) -> Any:
        artifact_path = self.model_dir / artifact_name
        if not artifact_path.exists():
            raise FileNotFoundError(f"Missing artifact: {artifact_path}")
        return joblib.load(artifact_path)

    @staticmethod
    def build_model_text(title: str, abstract: str) -> str:
        """Build model input text to match training-time preprocessing."""
        return f"{(title or '').strip()} {(abstract or '').strip()}".strip()

    def predict(self, title: str, abstract: str, top_k: int = 3) -> dict[str, Any]:
        """Predict category and optional class probabilities."""
        model_text = self.build_model_text(title, abstract)
        if not model_text:
            raise ValueError("Title and abstract cannot both be empty.")

        features = self.vectorizer.transform([model_text])
        pred_idx = self.model.predict(features)
        pred_label = self.label_encoder.inverse_transform(pred_idx)[0]

        result: dict[str, Any] = {"predicted_label": str(pred_label)}

        if hasattr(self.model, "predict_proba"):
            probs = self.model.predict_proba(features)[0]
            ranked = sorted(
                zip(self.label_encoder.classes_, probs),
                key=lambda item: item[1],
                reverse=True,
            )
            keep = max(1, int(top_k))
            result["top_probabilities"] = [
                {"label": str(label), "probability": float(prob)}
                for label, prob in ranked[:keep]
            ]

        return result