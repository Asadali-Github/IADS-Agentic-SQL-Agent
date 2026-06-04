"""OCI Generative AI embedding client for Oracle vector search."""

from __future__ import annotations

import email.utils
import os
import time
import urllib.request
from datetime import UTC, datetime

import oci
import oci.signer
from dotenv import load_dotenv
from oci.generative_ai_inference import GenerativeAiInferenceClient, models


class OCITextEmbeddingClient:
    """Create text embeddings with OCI Generative AI."""

    _clock_offset_seconds: float | None = None
    _patched_signer_clock = False

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
        self._patch_oci_signer_clock_if_needed()
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

    def _patch_oci_signer_clock_if_needed(self) -> None:
        """Use network time for OCI request signatures when Windows clock sync is unavailable."""
        if self.__class__._patched_signer_clock:
            return

        offset_seconds = self._network_clock_offset_seconds()
        self.__class__._clock_offset_seconds = offset_seconds
        if abs(offset_seconds) < 60:
            return

        original_formatdate = email.utils.formatdate

        def formatdate_with_network_offset(
            timeval: float | None = None,
            localtime: bool = False,
            usegmt: bool = False,
        ) -> str:
            adjusted_time = (timeval if timeval is not None else time.time()) + offset_seconds
            return original_formatdate(adjusted_time, localtime=localtime, usegmt=usegmt)

        oci.signer.email.utils.formatdate = formatdate_with_network_offset
        self.__class__._patched_signer_clock = True

    def _network_clock_offset_seconds(self) -> float:
        if self.__class__._clock_offset_seconds is not None:
            return self.__class__._clock_offset_seconds

        for url in ("https://www.oracle.com", "https://www.google.com"):
            try:
                request = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(request, timeout=5) as response:
                    date_header = response.headers.get("Date")
                if not date_header:
                    continue
                network_time = email.utils.parsedate_to_datetime(date_header)
                if network_time.tzinfo is None:
                    network_time = network_time.replace(tzinfo=UTC)
                local_time = datetime.now(UTC)
                return (network_time - local_time).total_seconds()
            except Exception:
                continue

        return 0.0
