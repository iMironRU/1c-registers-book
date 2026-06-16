# 📚 book-template

Шаблон репозитория для написания и публикации технических книг.

**Markdown → EPUB, FB2, PDF, DOCX, HTML, сайт** — всё через один скрипт и GitHub Actions.

---

## Что внутри

| Возможность | Описание |
|---|---|
| **`./book.sh`** | Единая точка входа: инициализация, статус, сборка, релиз, синхронизация |
| **SDD-процесс** | `spec/constitution.md` + `spec/specification.md` перед написанием |
| **Claude Code** | `CLAUDE.md` + slash-команды `/book-write`, `/book-analyze`, `/book-plan` |
| **Форматы** | EPUB, FB2, PDF A5/A4, DOCX, HTML, сайт (mdBook) — включаются галочками в `metadata.yaml` |
| **Статусы глав** | `draft / review / ready` в frontmatter каждого файла |
| **Релизы** | Тег `v*` → GitHub Actions собирает все форматы → Release |
| **Ночные сборки** | Автоматически, только если были коммиты, помечаются Pre-release |
| **Sync** | Еженедельная проверка обновлений шаблона, Issue + `./book.sh sync` |

---

## Быстрый старт

### 1. Создать книгу из шаблона

На GitHub: кнопка **Use this template → Create a new repository**.

Или через Git:
```bash
git clone https://github.com/iMironRU/book-template my-book
cd my-book
./book.sh init
```

### 2. Инициализация

```
./book.sh init
```

Скрипт спросит название, автора, язык, какие форматы нужны.
Или через флаги: `./book.sh init --title "Моя книга" --author "Иван Иванов"`

### 3. Заполнить спецификацию

```
spec/constitution.md    ← принципы книги: что ЕСТЬ и что НЕ ЕСТЬ
spec/specification.md   ← для кого, объём, метрики успеха
```

Это SDD-слой. Claude Code читает эти файлы перед написанием любого параграфа.

### 4. Писать

Каждый параграф — отдельный `.md` файл в `chapters/`:

```
chapters/
├── 00_vvedenie/
│   ├── 00-01_perviy_paragraf.md
│   └── 00-02_vtoroy.md
└── 01_glava/
    └── 01-01_...
```

Frontmatter обязателен:
```yaml
---
status: draft    # draft | review | ready
---
```

С Claude Code: `/book-write §1.1 тема параграфа`

### 5. Смотреть прогресс

```bash
./book.sh status
```

### 6. Собрать локально

```bash
./book.sh build          # все форматы включённые в metadata.yaml
./book.sh build ready    # только финальные главы
```

Требования: `pandoc`, `python3` + `pyyaml`, `mdbook` (для сайта).

### 7. Выпустить версию

```bash
./book.sh release
```

Скрипт спросит уровень (patch/minor/major) и changelog.
После `git push && git push --tags` GitHub Actions соберёт всё.

---

## Структура репозитория

```
book-template/
├── CLAUDE.md                      ← системный промпт для Claude Code
├── book.sh                        ← единая точка входа
├── metadata.yaml                  ← конфиг: форматы, версия, артефакты
├── book.toml                      ← конфиг mdBook
│
├── spec/
│   ├── constitution.md            ← принципы книги (заполнить первым)
│   ├── specification.md           ← для кого и о чём
│   └── decisions.md               ← лог принятых решений
│
├── docs/
│   ├── style-guide.md             ← требования к стилю параграфов
│   └── writing-workflow.md        ← описание SDD-процесса
│
├── .claude/commands/
│   ├── book-write.md              ← /book-write §N.N
│   ├── book-analyze.md            ← /book-analyze §N.N
│   └── book-plan.md               ← /book-plan модуль-N
│
├── .github/workflows/
│   ├── build-release.yml          ← триггер: git tag v*
│   ├── build-nightly.yml          ← ежедневно, только если были коммиты
│   └── check-template.yml         ← еженедельно, открывает Issue при обновлении
│
└── chapters/
    └── 00_intro/
        └── 00-01_primer.md
```

---

## Форматы и артефакты

Всё управляется через `metadata.yaml`:

```yaml
formats:
  epub:     true
  fb2:      true
  pdf_a5:   true
  pdf_a4:   false
  html:     true
  docx:     true
  site:     true    # GitHub Pages через mdBook

artifacts:
  - type: zip
    source: "code/"
    name: "code-examples"
```

---

## Версионирование книги

`MAJOR.MINOR.PATCH`:
- **PATCH** — исправления, уточнения
- **MINOR** — новые главы
- **MAJOR** — реорганизация структуры

Changelog пишет автор при релизе. Запятые и опечатки в него не попадают.

---

## Обновление шаблона

Еженедельный workflow открывает GitHub Issue если доступна новая версия.
Для применения: `./book.sh sync` — покажет изменённые файлы и спросит что применить.

---

## Требования

| Инструмент | Зачем | Установка |
|---|---|---|
| `pandoc` | Сборка EPUB, FB2, DOCX, HTML | [pandoc.org](https://pandoc.org/installing.html) |
| `python3` + `pyyaml` | Чтение metadata.yaml | `pip install pyyaml` |
| `mdbook` | Сборка сайта | [rust-lang.github.io/mdBook](https://rust-lang.github.io/mdBook/guide/installation.html) |
| `xelatex` | Сборка PDF | TeX Live: `texlive-xetex` |

В GitHub Actions всё устанавливается автоматически.

---

Создан как основа для серии технических книг [iMironRU](https://github.com/iMironRU).
Использует [Pandoc](https://pandoc.org/) + [mdBook](https://rust-lang.github.io/mdBook/).
