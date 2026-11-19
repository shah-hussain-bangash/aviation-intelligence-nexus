"""Bounded, local historical-scenario inference; never operational approval."""

from datetime import date
import hashlib
import json
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    carrier: str = Field(pattern=r"^[A-Z0-9]{2,3}$")
    origin: str = Field(pattern=r"^[A-Z]{3}$")
    destination: str = Field(pattern=r"^[A-Z]{3}$")
    flight_date: date
    scheduled_departure: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")

    @field_validator("flight_date")
    @classmethod
    def historical_window(cls, value):
        if not date(2025, 1, 1) <= value <= date(2025, 5, 31):
            raise ValueError("Research scenarios are restricted to January-May 2025")
        return value

    @model_validator(mode="after")
    def distinct_airports(self):
        if self.origin == self.destination:
            raise ValueError("Origin and destination must differ")
        return self


class ScenarioOutOfScope(ValueError):
    def __init__(self, fields):
        self.fields = fields


class ResearchPredictor:
    def __init__(self, directory: Path):
        self.directory = directory
        self._lock = Lock()
        self._digest = None
        self._model = None

    def predict(self, scenario: Scenario):
        # A single local inference at a time; fixed artifact path, never user-supplied models.
        with self._lock:
            report = json.loads((self.directory / "report.json").read_text(encoding="utf-8"))
            artifact = self.directory / "model.joblib"
            with artifact.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if (digest != report.get("artifact_sha256") or report.get("model_version") != "delay-v2" or
                report.get("release_assessment", {}).get("research_gate_passed") is not True):
                raise RuntimeError("Verified research model unavailable")
            import joblib
            import numpy as np
            import pandas as pd
            from threadpoolctl import threadpool_limits
            if self._model is None or self._digest != digest:
                # Only load the locally created artifact whose report integrity was checked above.
                self._model = joblib.load(artifact)
                self._digest = digest
            encoder = self._model.named_steps["features"].named_transformers_["categories"]
            fields = ["carrier", "origin", "destination"]
            unknown = [field for field, vocabulary in zip(fields, encoder.categories_)
                       if getattr(scenario, field) not in vocabulary]
            if unknown:
                raise ScenarioOutOfScope(unknown)
            hour, minute = map(int, scenario.scheduled_departure.split(":"))
            frame = pd.DataFrame([{"carrier": scenario.carrier, "origin": scenario.origin,
                "destination": scenario.destination, "scheduled_departure_hour": str(hour),
                "scheduled_departure_minute": str(minute), "day_of_week": str(scenario.flight_date.isoweekday())}])
            with threadpool_limits(limits=2):
                probability = float(self._model.predict_proba(frame)[0, 1])
            if not np.isfinite(probability) or not 0 <= probability <= 1:
                raise RuntimeError("Invalid model output")
            warnings = ["Historical schedule scenario only; not confirmation that this flight existed.",
                "Probability applies conditional on a completed, non-diverted flight with an observed arrival delay.",
                "US domestic research model; not approved for airline decisions or UAE operations."]
            period = "training" if scenario.flight_date.month <= 3 else "validation" if scenario.flight_date.month == 4 else "evaluated test"
            warnings.append(f"This date belongs to the {period} period; this scenario is not a new independent evaluation.")
            for field, categories in zip(fields, encoder.infrequent_categories_):
                if categories is not None and getattr(scenario, field) in categories:
                    warnings.append(f"{field} is grouped with infrequent training categories.")
            return {"model_version": "delay-v2", "artifact_sha256": digest,
                "arrival_delay_15_probability": probability, "scenario": scenario.model_dump(mode="json"),
                "research_only": True, "operational_serving_approved": False,
                "warnings": warnings}
