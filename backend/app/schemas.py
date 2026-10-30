from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


class RfmParams(BaseModel):
    engine: Literal["auto", "spark", "pandas"] = "auto"


class ClusterParams(BaseModel):
    k: Optional[int] = Field(None, ge=2, le=12, description="Fixed k; omit to pick the best silhouette in [k_min, k_max]")
    k_min: int = Field(2, ge=2, le=10)
    k_max: int = Field(8, ge=3, le=12)

    @model_validator(mode="after")
    def _range(self):
        if self.k_min >= self.k_max:
            raise ValueError("k_min must be smaller than k_max")
        return self


class BasketParams(BaseModel):
    min_support: float = Field(0.02, gt=0, le=1)
    min_confidence: float = Field(0.3, gt=0, le=1)
    min_lift: float = Field(1.0, ge=0)
    top_n: int = Field(150, ge=10, le=500)
    max_len: int = Field(3, ge=2, le=4)


class ForecastParams(BaseModel):
    horizon: int = Field(28, ge=1, le=28)
    test_days: int = Field(28, ge=14, le=90)


PARAM_MODELS = {"rfm": RfmParams, "clustering": ClusterParams, "basket": BasketParams, "forecast": ForecastParams}


class RunRequest(BaseModel):
    run_type: Literal["rfm", "clustering", "basket", "forecast"]
    params: dict = Field(default_factory=dict)
