#!/usr/bin/env python3
"""Эксперимент: прогоняем один параграф через матрицу OpenAI моделей × ролей.

Usage:
    python3 scripts/experiment_gpt.py A1

Output: reviews/<label>-experiment/<model>__<role>.md
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
    "B3.5": "chapters/02_ruki/02-04_pishu_chitayu.md",
}

# Матрица: модели × роли
MODELS = ["gpt-5.5", "gpt-4.1", "o3"]
ROLES  = ["structure", "metaphor", "tone"]


def load_env():
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
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


def call_openai(model, system_prompt, user_content):
    """Универсальный вызов. Для reasoning-моделей (o-серия) убираем temperature
    и max_tokens, добавляем max_completion_tokens."""
    key = os.environ["OPENAI_API_KEY"]
    is_reasoning = model.startswith(("o1", "o3", "o4"))
    is_gpt5      = model.startswith("gpt-5")

    if is_reasoning:
        body = {
            "model": model,
            "messages": [
                {"role": "user", "content": f"{system_prompt}\n\n---\n\n{user_content}"},
            ],
            "max_completion_tokens": 8000,
        }
    elif is_gpt5:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            "max_completion_tokens": 8000,
        }
    else:
        body = {
            "model": model,
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


def build_context(paragraph_text, paragraph_label):
    constitution  = (ROOT / "spec" / "constitution.md").read_text()
    specification = (ROOT / "spec" / "specification.md").read_text()
    claude_md     = (ROOT / "CLAUDE.md").read_text()
    return f"""# КОНТЕКСТ КНИГИ

## CLAUDE.md
```markdown
{claude_md}
```

## spec/constitution.md
```markdown
{constitution}
```

## spec/specification.md
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


def main():
    if len(sys.argv) < 2:
        sys.exit(f"Usage: {sys.argv[0]} <§ shortcut>\nКлючи: {', '.join(PARA_MAP)}")
    load_env()

    label = sys.argv[1]
    if label not in PARA_MAP:
        sys.exit(f"Неизвестный шорткат: {label}")
    rel_path = PARA_MAP[label]
    paragraph_text = (ROOT / rel_path).read_text()
    context = build_context(paragraph_text, f"§{label}  ({rel_path})")

    role_prompts = {
        role: (PROMPTS / f"openai-{role}.md").read_text()
        for role in ROLES
    }

    out_dir = REVIEWS / f"{label}-experiment"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Матрица заданий
    jobs = [(model, role) for model in MODELS for role in ROLES]
    print(f"\n→ Параграф: §{label}")
    print(f"→ Матрица: {len(MODELS)} моделей × {len(ROLES)} ролей = {len(jobs)} прогонов")
    print(f"→ Запускаю параллельно (max 4 потока)…\n")

    def run(model, role):
        t0 = time.monotonic()
        result = call_openai(model, role_prompts[role], context)
        return result, time.monotonic() - t0

    results = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(run, m, r): (m, r) for m, r in jobs}
        for fut in futures:
            m, r = futures[fut]
            try:
                content, secs = fut.result()
                results[(m, r)] = content
                print(f"  ✓ {m:<14} × {r:<10} {len(content):>6} симв.  ({secs:.1f}s)")
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                results[(m, r)] = f"# ОШИБКА\n\n```\n{err}\n```\n"
                print(f"  ✗ {m:<14} × {r:<10} {err[:80]}")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for (model, role), content in results.items():
        fname = f"{model}__{role}.md"
        path = out_dir / fname
        path.write_text(
            f"<!-- generated {stamp} | model={model} | role={role} -->\n\n{content}\n"
        )

    print(f"\nГотово. {len(jobs)} файлов в {out_dir.relative_to(ROOT)}/\n")


if __name__ == "__main__":
    main()
