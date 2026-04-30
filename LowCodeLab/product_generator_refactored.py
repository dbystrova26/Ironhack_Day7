"""
Product Description Generator - Refactored Version

This script loads product data from JSON, validates it with Pydantic, generates
product descriptions through OpenAI, and writes the results to disk.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from openai import APIError, AuthenticationError, OpenAI, RateLimitError
from pydantic import BaseModel, Field, ValidationError

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from pydantic import field_validator

    PYDANTIC_V2 = True
except ImportError:
    from pydantic import validator

    PYDANTIC_V2 = False


LOG_FILE = f"product_generator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


class Product(BaseModel):
    id: str
    name: str
    category: str
    price: float
    features: List[str] = Field(default_factory=list)

    if PYDANTIC_V2:

        @field_validator("price")
        @classmethod
        def price_must_be_positive(cls, value: float) -> float:
            if value <= 0:
                raise ValueError("Price must be positive")
            return value

    else:

        @validator("price")
        def price_must_be_positive(cls, value: float) -> float:
            if value <= 0:
                raise ValueError("Price must be positive")
            return value


class OpenAIWrapper:
    """Small OpenAI client wrapper with retry logic and explicit error logging."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        max_retries: int = 3,
        base_delay_seconds: float = 1.0,
    ) -> None:
        if load_dotenv is not None:
            load_dotenv()

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds

        if not self.api_key:
            message = (
                "OpenAIWrapper.__init__: OPENAI_API_KEY is missing. "
                "Set it in your environment before calling the API."
            )
            logger.error(message)
            raise ValueError(message)

        self.client = OpenAI(api_key=self.api_key)
        logger.info("OpenAIWrapper initialized with model=%s", self.model)

    def create_chat_completion(self, prompt: str) -> Any:
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "OpenAIWrapper.create_chat_completion: API attempt %s/%s",
                    attempt,
                    self.max_retries,
                )
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                )
            except AuthenticationError:
                logger.exception(
                    "OpenAIWrapper.create_chat_completion: authentication failed; "
                    "check OPENAI_API_KEY."
                )
                raise
            except RateLimitError as error:
                last_error = error
                logger.warning(
                    "OpenAIWrapper.create_chat_completion: rate limit on attempt %s/%s.",
                    attempt,
                    self.max_retries,
                    exc_info=True,
                )
            except (APIError, httpx.TimeoutException, httpx.ConnectError) as error:
                last_error = error
                logger.warning(
                    "OpenAIWrapper.create_chat_completion: retryable API/network "
                    "error on attempt %s/%s.",
                    attempt,
                    self.max_retries,
                    exc_info=True,
                )

            if attempt < self.max_retries:
                delay = self.base_delay_seconds * (2 ** (attempt - 1))
                logger.info(
                    "OpenAIWrapper.create_chat_completion: retrying in %.1f seconds.",
                    delay,
                )
                time.sleep(delay)

        message = (
            "OpenAIWrapper.create_chat_completion: all retry attempts failed "
            f"after {self.max_retries} attempts."
        )
        logger.error(message, exc_info=last_error)
        raise RuntimeError(message) from last_error


def load_json_file(json_file: str) -> Dict[str, Any]:
    file_path = Path(json_file)
    logger.info("load_json_file: loading %s", file_path)

    try:
        with file_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as error:
        logger.exception(
            "load_json_file: file not found at %s. Current working directory: %s",
            file_path,
            Path.cwd(),
        )
        raise FileNotFoundError(
            f"load_json_file: could not find JSON file '{file_path}' "
            f"from working directory '{Path.cwd()}'."
        ) from error
    except json.JSONDecodeError as error:
        logger.exception(
            "load_json_file: invalid JSON in %s at line %s, column %s.",
            file_path,
            error.lineno,
            error.colno,
        )
        raise ValueError(
            f"load_json_file: invalid JSON in '{file_path}' at "
            f"line {error.lineno}, column {error.colno}: {error.msg}"
        ) from error
    except OSError as error:
        logger.exception("load_json_file: failed reading %s", file_path)
        raise OSError(f"load_json_file: failed reading '{file_path}': {error}") from error


def validate_product_data(data: Dict[str, Any]) -> List[Product]:
    logger.info("validate_product_data: validating product payload")

    if "products" not in data:
        message = "validate_product_data: JSON object must contain a 'products' key."
        logger.error(message)
        raise ValueError(message)

    if not isinstance(data["products"], list):
        message = "validate_product_data: 'products' must be a list."
        logger.error(message)
        raise TypeError(message)

    products: List[Product] = []

    for index, item in enumerate(data["products"]):
        try:
            products.append(Product(**item))
        except ValidationError as error:
            logger.error(
                "validate_product_data: product at index %s failed validation.",
                index,
                exc_info=True,
            )
            for validation_error in error.errors():
                field = ".".join(str(part) for part in validation_error["loc"])
                logger.error(
                    "validate_product_data: index=%s field=%s error=%s",
                    index,
                    field,
                    validation_error["msg"],
                )

    if not products:
        message = "validate_product_data: no valid products were found."
        logger.error(message)
        raise ValueError(message)

    logger.info(
        "validate_product_data: %s valid product(s), %s invalid product(s)",
        len(products),
        len(data["products"]) - len(products),
    )
    return products


def create_product_prompt(product: Product) -> str:
    logger.debug("create_product_prompt: building prompt for product_id=%s", product.id)
    features = ", ".join(product.features) if product.features else "No listed features"

    return f"""Create a product description for:
Name: {product.name}
Category: {product.category}
Price: ${product.price:.2f}
Features: {features}

Generate a compelling product description."""


def parse_api_response(response: Any) -> str:
    logger.debug("parse_api_response: parsing OpenAI response")

    try:
        description = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as error:
        logger.exception("parse_api_response: unexpected API response structure.")
        raise ValueError(
            "parse_api_response: OpenAI response did not contain "
            "choices[0].message.content."
        ) from error

    if not description or not description.strip():
        message = "parse_api_response: OpenAI returned an empty description."
        logger.error(message)
        raise ValueError(message)

    return description.strip()


def format_output(product: Product, description: str) -> Dict[str, str]:
    logger.debug("format_output: formatting product_id=%s", product.id)
    return {
        "product_id": product.id,
        "name": product.name,
        "description": description,
    }


def save_results(results: List[Dict[str, str]], output_file: str = "results.json") -> None:
    output_path = Path(output_file)
    logger.info("save_results: writing %s result(s) to %s", len(results), output_path)

    try:
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(results, file, indent=2)
    except OSError as error:
        logger.exception("save_results: failed writing %s", output_path)
        raise OSError(f"save_results: failed writing '{output_path}': {error}") from error


def generate_product_descriptions(
    json_file: str,
    output_file: str = "results.json",
    openai_client: Optional[OpenAIWrapper] = None,
) -> List[Dict[str, str]]:
    logger.info("generate_product_descriptions: starting for input=%s", json_file)

    data = load_json_file(json_file)
    products = validate_product_data(data)
    wrapper = openai_client or OpenAIWrapper()
    results: List[Dict[str, str]] = []

    for product in products:
        try:
            prompt = create_product_prompt(product)
            response = wrapper.create_chat_completion(prompt)
            description = parse_api_response(response)
            results.append(format_output(product, description))
            logger.info(
                "generate_product_descriptions: generated description for product_id=%s",
                product.id,
            )
        except Exception:
            logger.exception(
                "generate_product_descriptions: failed while processing "
                "product_id=%s name=%s",
                product.id,
                product.name,
            )
            raise

    save_results(results, output_file)
    logger.info("generate_product_descriptions: completed successfully")
    return results


if __name__ == "__main__":
    generate_product_descriptions("products.json")
