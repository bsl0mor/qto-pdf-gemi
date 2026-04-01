"""
config.py — Centralized configuration for QTO-AI pipeline.
"""
import os

API_KEY   = os.environ.get("GEMINI_API_KEY", "AIzaSyAEf3myy42MZRDChyd2kRRrXDusTFG0rEY")
MODEL     = "gemini-2.5-flash"
MODEL_PRO = "gemini-2.5-pro"
URL       = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
URL_PRO   = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_PRO}:generateContent?key={API_KEY}"
