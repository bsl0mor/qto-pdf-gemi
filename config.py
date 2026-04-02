"""
config.py — Centralized configuration for QTO pipeline.
Set GEMINI_API_KEY in your environment before use (no hardcoded key).
"""
import os

API_KEY   = os.environ.get("GEMINI_API_KEY", "")
MODEL     = "gemini-2.5-flash"
MODEL_PRO = "gemini-2.5-pro"
URL       = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
URL_PRO   = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_PRO}:generateContent?key={API_KEY}"
