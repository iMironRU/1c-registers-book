#!/usr/bin/env python3
"""Прогон параграфа книги через трёх внешних редакторов параллельно.

Usage:
    python3 scripts/review.py A0
    python3 scripts/review.py B3.5
    python3 scripts/review.py chapters/02_ruki/02-04_pishu_chitayu.md

Output: reviews/<label>/{deepseek,openai,gemini}.md
"""
import os
import sys
import json
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


def http_post(url, headers, body, timeout=600, retries=3):
    import time
    data = json.dumps(body).encode("utf-8")
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            last_err = f"HTTP {e.code}: {err_body[:1000]}"
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
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


def call_openai(system_prompt, user_content):
    key = os.environ["OPENAI_API_KEY"]
    body = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": 8000,
    }
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
    constitution   = (ROOT / "spec" / "constitution.md").read_text()
    specification  = (ROOT / "spec" / "specification.md").read_text()
    claude_md      = (ROOT / "CLAUDE.md").read_text()
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
    if len(sys.argv) < 2:
        sys.exit(
            f"Usage: {sys.argv[0]} <§ shortcut or file path>\n"
            f"Шорткаты: {', '.join(PARA_MAP.keys())}"
        )
    load_env()

    rel_path, label = resolve_path(sys.argv[1])
    para_file = ROOT / rel_path
    paragraph_text = para_file.read_text()
    context = build_context(paragraph_text, f"§{label}  ({rel_path})")

    prompts = {
        "deepseek": (PROMPTS / "deepseek-fact.md").read_text(),
        "openai":   (PROMPTS / "openai-style.md").read_text(),
        "gemini":   (PROMPTS / "gemini-adversary.md").read_text(),
    }

    out_dir = REVIEWS / label
    out_dir.mkdir(parents=True, exist_ok=True)

    tasks = {
        "deepseek": (call_deepseek, "DeepSeek — фактчек 1С"),
        "openai":   (call_openai,   "GPT-4o — стиль и канон"),
        "gemini":   (call_gemini,   "Gemini 2.5 Pro — адверсар + читатель"),
    }

    print(f"\n→ Параграф: §{label}  ({rel_path})")
    print(f"→ Запускаю 3 редактора параллельно…\n")

    def run(name):
        fn, _ = tasks[name]
        return fn(prompts[name], context)

    results = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(run, name): name for name in tasks}
        for fut in futures:
            name = futures[fut]
            try:
                results[name] = fut.result()
                _, role_label = tasks[name]
                print(f"  ✓ {role_label}: {len(results[name])} симв.")
            except Exception as e:
                _, role_label = tasks[name]
                err = f"{type(e).__name__}: {e}"
                results[name] = f"# ОШИБКА вызова\n\n```\n{err}\n```\n"
                print(f"  ✗ {role_label}: {err}")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for name, content in results.items():
        path = out_dir / f"{name}.md"
        path.write_text(f"<!-- generated {stamp} -->\n\n{content}\n")
        print(f"  → {path.relative_to(ROOT)}")

    print(
        f"\nГотово. Отчёты в {out_dir.relative_to(ROOT)}/. "
        f"Дальше — Claude читает три файла и пишет synthesis.md.\n"
    )


if __name__ == "__main__":
    main()
