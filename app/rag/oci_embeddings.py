"""OCI Generative AI embedding client for Oracle vector search."""

from __future__ import annotations

import os

import oci
from dotenv import load_dotenv
from oci.generative_ai_inference import GenerativeAiInferenceClient, models


class OCITextEmbeddingClient:
    """Create text embeddings with OCI Generative AI."""

    def __init__(
        self,
        compartment_id: str | None = None,
        model_id: str | None = None,
        region: str | None = None,
        config_path: str | None = None,
        config_profile: str | None = None,
    ) -> None:
        load_dotenv()
        self.compartment_id = compartment_id or os.getenv("OCI_COMPARTMENT_ID")
        if not self.compartment_id:
            raise RuntimeError("OCI_COMPARTMENT_ID is not set.")

        self.model_id = model_id or os.getenv("OCI_EMBED_MODEL_ID", "cohere.embed-english-v3.0")
        self.config_path = config_path or os.getenv("OCI_CONFIG_PATH")
        self.config_profile = config_profile or os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")
        if not self.config_path:
            raise RuntimeError("OCI_CONFIG_PATH is not set.")

        self.config = oci.config.from_file(self.config_path, self.config_profile)
        self.region = region or os.getenv("OCI_REGION") or self.config.get("region")
        self.client = GenerativeAiInferenceClient(
            self.config,
            service_endpoint=f"https://inference.generativeai.{self.region}.oci.oraclecloud.com",
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed document texts for storage."""
        return self._embed(texts, models.EmbedTextDetails.INPUT_TYPE_SEARCH_DOCUMENT)

    def embed_query(self, text: str) -> list[float]:
        """Embed a user question for search."""
        return self._embed([text], models.EmbedTextDetails.INPUT_TYPE_SEARCH_QUERY)[0]

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        details = models.EmbedTextDetails(
            compartment_id=self.compartment_id,
            serving_mode=models.OnDemandServingMode(model_id=self.model_id),
            inputs=texts,
            input_type=input_type,
            truncate=models.EmbedTextDetails.TRUNCATE_END,
        )
        response = self.client.embed_text(details)
        embeddings = response.data.embeddings
        if not embeddings:
            raise RuntimeError("OCI embedding service returned no embeddings.")
        return embeddings
