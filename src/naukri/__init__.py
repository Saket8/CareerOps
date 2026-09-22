"""Naukri access module."""

from src.naukri.interface import BaseNaukriClient, SafetyBarrierException
from src.naukri.browser_adapter import NaukriBrowserAdapter

__all__ = ["BaseNaukriClient", "SafetyBarrierException", "NaukriBrowserAdapter"]
