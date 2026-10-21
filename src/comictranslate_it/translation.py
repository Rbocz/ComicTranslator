"""English-to-Italian page translation. No synthetic 'translation' when API unavailable."""
from __future__ import annotations
import json
import os
from .models import Page


class TranslationError(RuntimeError):
    pass


def translate_page(page: Page, glossary: dict[str,str] | None=None,
                   recent_context: list[str] | None=None, model: str="gpt-4.1-mini",
                   base_url: str="https://api.openai.com/v1") -> dict[str,str]:
    """Use an OpenAI-compatible chat endpoint and validate IDs. No image is uploaded.

    Each call sends OCR text from ONE page plus the supplied short contextual history.
    The user must inspect machine translations before approving the visual replacement.
    """
    try:
        import requests
    except ImportError as exc:
        raise TranslationError("Per usare le API: pip install comictranslate-it[cloud]") from exc
    api_key=os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise TranslationError("Manca OPENAI_API_KEY; traduzione automatica non eseguita")
    source=[{"id":r.id,"text":r.original,"type":r.kind} for r in page.regions if r.original.strip()]
    if not source:
        return {}
    instructions=(
        "Sei un traduttore editoriale specializzato in comic book USA. Traduci dall'inglese all'italiano "
        "naturale, preservando significato, continuità, tono, nomi propri, enfasi e registro. "
        "Usa il glossario esattamente quando pertinente. Privilegia formulazioni concise senza "
        "omettere informazioni. NON aggiungere o dividere blocchi. Rispondi SOLO con JSON "
        "nel formato {\"translations\": [{\"id\": \"...\", \"it\": \"...\"}]}."
    )
    payload={"model":model,"temperature":0.2,"response_format":{"type":"json_object"},
        "messages":[{"role":"system","content":instructions},
                    {"role":"user","content":json.dumps({"glossary":glossary or {},
                     "previous_pages":(recent_context or [])[-3:],"blocks":source},ensure_ascii=False)}]}
    try:
        response=requests.post(base_url.rstrip("/")+"/chat/completions",
            headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},
            json=payload,timeout=90)
        response.raise_for_status()
        parsed=json.loads(response.json()["choices"][0]["message"]["content"])
        entries=parsed["translations"]
    except (ValueError,KeyError,IndexError,requests.RequestException,TypeError) as exc:
        raise TranslationError(f"Risposta API non valida: {type(exc).__name__}: {exc}") from exc
    expected={r["id"] for r in source}
    result={}
    for entry in entries:
        ident=entry.get("id")
        value=entry.get("it")
        if ident not in expected or not isinstance(value,str) or not value.strip() or ident in result:
            raise TranslationError("L'API ha restituito ID o traduzioni non validi")
        result[ident]=value.strip()
    if set(result)!=expected:
        raise TranslationError("L'API ha omesso alcuni balloon: nessun risultato parziale applicato")
    return result
