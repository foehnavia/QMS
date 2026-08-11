"""Наполнение БД: идемпотентный сид справочников и синтетический датасет."""

from .reference import GENERAL, REFERENCE_SEED, ref, seed_reference
from .synthetic import build_synthetic

__all__ = ["GENERAL", "REFERENCE_SEED", "ref", "seed_reference", "build_synthetic"]
