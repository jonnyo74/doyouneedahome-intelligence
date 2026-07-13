"""Loads and lightly validates the YAML files under config/."""

import functools
import os

import yaml

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")


def _load_yaml(filename: str) -> dict:
    path = os.path.join(CONFIG_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@functools.lru_cache(maxsize=1)
def load_site_config() -> dict:
    return _load_yaml("site.yaml")


@functools.lru_cache(maxsize=1)
def load_cities_config() -> dict:
    data = _load_yaml("cities.yaml")
    slugs = [c["slug"] for c in data["cities"]]
    if len(slugs) != len(set(slugs)):
        raise ValueError("Duplicate city slug found in config/cities.yaml")
    return data


@functools.lru_cache(maxsize=1)
def load_keywords_config() -> dict:
    return _load_yaml("keywords.yaml")


@functools.lru_cache(maxsize=1)
def load_content_rules() -> dict:
    return _load_yaml("content_rules.yaml")


def get_city(slug: str) -> dict | None:
    for city in load_cities_config()["cities"]:
        if city["slug"] == slug:
            return city
    return None


def tier1_cities() -> list[dict]:
    return [c for c in load_cities_config()["cities"] if c.get("extra_detail")]
