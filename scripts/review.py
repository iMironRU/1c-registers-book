#!/usr/bin/env python3
"""Прогон параграфа книги через обойму редакторов параллельно.

Обойма:
  - DeepSeek (deepseek-chat)        — фактчек платформы 1С
  - GPT-5.5  (structure)            — архитектура текста
  - GPT-5.5  (metaphor)             — устойчивость образов
  - GPT-5.5  (tone)                 — звучание (опционально, флаг --tone)
  - Gemini 2.5 Flash                — адверсар + читатель-первокурсник

Usage:
    python3 scripts/review.py A0
    python3 scripts/review.py B3.5 --tone
    python3 scripts/review.py chapters/02_ruki/02-04_pishu_chitayu.md

Output: reviews/<label>/{deepseek,gpt55-structure,gpt55-metaphor,gpt55-tone,gemini}.md
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

ROOT = Path(__file__).parent.parent.resolve()
PROMPTS = ROOT / "scripts" / "prompts"
REVIEWS = ROOT / "reviews"

PARA_MAP = {
    "A0":   "chapters/01_koncept/01-01_zachem_registr.md",
    "A1":   "chapters/01_koncept/01-02_registr_v_grammatike.md",
    "A2":   "chapters/01_koncept/01-03_kryuchok_istorii.md",
    "A3":   "chapters/01_koncept/01-04_obshchij_skelet.md",
    "A4":   "chapters/01_koncept/01-05_registry_na_bytovom_domene.md",
    "B1":   "chapters/02_ruki/02-01_pervyj_zahod_v_konfigurator.md",
    "B2":   "chapters/02_ruki/02-02_izmerenie_ili_rekvizit.md",
    "B3":   "chapters/02_ruki/02-03_zapis_provedenie.md",
    "B3.5": "chapters/02_ruki/02-04_pishu_chitayu.md",
    "B4":   "chapters/02_ruki/02-05_vyborka_zapros_vt.md",
    "C1":   "chapters/03_predmetka/03-01_most_vo_vtoroj_domen.md",
    "C2":   "chapters/03_predmetka/03-02_vtoroj_zahod_rb_rr.md",
    "C3":   "chapters/03_predmetka/03-03_vybor_registra.md",
    "C4":   "chapters/03_predmetka/03-04_vybor_na_praktike.md",
    "C5":   "chapters/03_predmetka/03-05_istoriya_celikom.md",
}


def load_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        sys.exit("Error: .env not found in repo root.")
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def http_post(url, headers, body, timeout=900, retries=3):
    data = json.dumps(body).encode("utf-8")
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            last_err = f"HTTP {e.code}: {err_body[:1500]}"
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(10 * (attempt + 1))
                continue
            raise RuntimeError(last_err) from None
    raise RuntimeError(last_err)


def call_deepseek(system_prompt, user_content):
    key = os.environ["DEEPSEEK_API_KEY"]
    body = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": 8000,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    resp = http_post("https://api.deepseek.com/v1/chat/completions", headers, body)
    return resp["choices"][0]["message"]["content"]


def call_openai(model, system_prompt, user_content):
    """GPT-5.x семья использует max_completion_tokens вместо max_tokens."""
    key = os.environ["OPENAI_API_KEY"]
    is_gpt5 = model.startswith("gpt-5")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
    }
    if is_gpt5:
        body["max_completion_tokens"] = 8000
    else:
        body["temperature"] = 0.3
        body["max_tokens"] = 8000
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    resp = http_post("https://api.openai.com/v1/chat/completions", headers, body)
    return resp["choices"][0]["message"]["content"]


def call_gemini(system_prompt, user_content):
    key = os.environ["GEMINI_API_KEY"]
    model = "gemini-2.5-flash"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_content}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8000},
    }
    headers = {"Content-Type": "application/json"}
    resp = http_post(url, headers, body)
    cands = resp.get("candidates") or []
    if not cands:
        return f"# Gemini вернул пустой ответ\n\n```\n{json.dumps(resp)[:2000]}\n```"
    parts = cands[0].get("content", {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts)


def build_context(paragraph_text, paragraph_label):
    constitution  = (ROOT / "spec" / "constitution.md").read_text()
    specification = (ROOT / "spec" / "specification.md").read_text()
    claude_md     = (ROOT / "CLAUDE.md").read_text()
    return f"""# КОНТЕКСТ КНИГИ

## CLAUDE.md (рабочие соглашения, канон, стиль)

```markdown
{claude_md}
```

## spec/constitution.md (контракт книги)

```markdown
{constitution}
```

## spec/specification.md (целевой читатель и метрики)

```markdown
{specification}
```

---

# ПАРАГРАФ НА ПРОВЕРКУ: {paragraph_label}

```markdown
{paragraph_text}
```

---

Дай отчёт по своей роли строго в указанном формате. Отвечай по-русски.
"""


def resolve_path(arg):
    if arg in PARA_MAP:
        return PARA_MAP[arg], arg
    p = Path(arg)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        sys.exit(
            f"Error: '{arg}' — нет в шорткатах PARA_MAP и не существует как файл.\n"
            f"Известные шорткаты: {', '.join(PARA_MAP.keys())}"
        )
    rel = p.resolve().relative_to(ROOT).as_posix()
    for label, mapped in PARA_MAP.items():
        if mapped == rel:
            return rel, label
    return rel, p.stem


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        sys.exit(
            f"Usage: {sys.argv[0]} <§ shortcut or path> [--tone]\n"
            f"Шорткаты: {', '.join(PARA_MAP)}"
        )
    load_env()

    rel_path, label = resolve_path(args[0])
    para_file = ROOT / rel_path
    paragraph_text = para_file.read_text()
    context = build_context(paragraph_text, f"§{label}  ({rel_path})")

    # Обойма: имя → (callable, описание, имя-файла-вывода)
    GPT5 = "gpt-5.5"

    def gpt55_role(role):
        def f(p): return call_openai(GPT5, p, context)
        return f

    editors = {
        "deepseek": (
            lambda: call_deepseek((PROMPTS / "deepseek-fact.md").read_text(), context),
            "DeepSeek — фактчек 1С",
        ),
        "gpt55-structure": (
            lambda: gpt55_role("structure")((PROMPTS / "openai-structure.md").read_text()),
            "GPT-5.5 — структура",
        ),
        "gpt55-metaphor": (
            lambda: gpt55_role("metaphor")((PROMPTS / "openai-metaphor.md").read_text()),
            "GPT-5.5 — метафоры",
        ),
        "gemini": (
            lambda: call_gemini((PROMPTS / "gemini-adversary.md").read_text(), context),
            "Gemini — адверсар + читатель",
        ),
    }
    if "--tone" in flags:
        editors["gpt55-tone"] = (
            lambda: gpt55_role("tone")((PROMPTS / "openai-tone.md").read_text()),
            "GPT-5.5 — тон и ритм",
        )

    out_dir = REVIEWS / label
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n→ Параграф: §{label}  ({rel_path})")
    print(f"→ Редакторы: {len(editors)}  (параллельно)\n")

    results = {}
    with ThreadPoolExecutor(max_workers=len(editors)) as ex:
        futures = {ex.submit(fn): (name, lbl) for name, (fn, lbl) in editors.items()}
        for fut in futures:
            name, lbl = futures[fut]
            t0 = time.monotonic()
            try:
                results[name] = fut.result()
                secs = time.monotonic() - t0
                print(f"  ✓ {lbl:<36} {len(results[name]):>6} симв.  ({secs:.1f}s)")
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                results[name] = f"# ОШИБКА вызова\n\n```\n{err[:2000]}\n```\n"
                print(f"  ✗ {lbl:<36} {err[:80]}")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for name, content in results.items():
        path = out_dir / f"{name}.md"
        path.write_text(f"<!-- generated {stamp} -->\n\n{content}\n")
        print(f"  → {path.relative_to(ROOT)}")

    print(
        f"\nГотово. Отчёты в {out_dir.relative_to(ROOT)}/. "
        f"Дальше — Claude собирает synthesis.md.\n"
    )


if __name__ == "__main__":
    main()
