# Дообучение LLM для диагностики инцидентов ISP

Пошаговая инструкция по созданию модели технической поддержки интернет-провайдера.

---

## Содержание

1. [Цели и требования](#1-цели-и-требования)
2. [Выбор базовой модели](#2-выбор-базовой-модели)
3. [Подготовка данных](#3-подготовка-данных)
4. [Окружение и зависимости](#4-окружение-и-зависимости)
5. [Конфигурация обучения](#5-конфигурация-обучения)
6. [Запуск обучения](#6-запуск-обучения)
7. [Оценка качества](#7-оценка-качества)
8. [Деплой](#8-деплой)
9. [Чеклист](#9-чеклист)

---

## 1. Цели и требования

### Задача модели
- Классифицировать тип инцидента по описанию пользователя
- Предлагать пошаговую диагностическую цепочку
- Определять причину и рекомендовать решение
- Работать на русском языке

### Примеры инцидентов
| Категория | Примеры |
|-----------|---------|
| Нет интернета | PPPoE не поднимается, проблема с DHCP, обрыв на линии |
| Низкая скорость | Переустройство, проблема с Wi-Fi, ограничение на порту |
| Маршрутизация | DNS не отвечает, потеря пакетов, асимметрия |
| Оборудование | Неисправность OLT,ONT, свитча, кабеля |
| Биллинг | Блокировка за неоплату, тариф не активирован |

### Аппаратные требования
| Вариант | GPU | RAM | Время обучения (7B, 10K примеров) |
|---------|-----|-----|-----------------------------------|
| QLoRA | 1x RTX 4090 (24GB) | 32GB | ~2-3 часа |
| QLoRA | 1x A100 (40GB) | 64GB | ~1-2 часа |
| LoRA | 2x A100 (80GB) | 128GB | ~1-2 часа |

---

## 2. Выбор базовой модели

### Приоритет: Qwen 2.5 7B

```
Qwen/Qwen2.5-7B-Instruct
```

**Почему Qwen 2.5 7B:**
- Сильная поддержка русского языка
- Хорошие способности к рассуждениям (reasoning)
- Контекстное окно 128K токенов
- Оптимальный размер для QLoRA на consumer GPU
- Хорошо поддаётся fine-tuning

### Альтернативы

| Модель | Для чего выбирать |
|--------|-------------------|
| `Qwen/Qwen2.5-14B-Instruct` | Если нужна максимальная точность (требует 2x A100) |
| `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` | Если критична цепочка рассуждений |
| `mistralai/Mistral-7B-Instruct-v0.3` | Если нужен быстрый инференс |

---

## 3. Подготовка данных

### 3.1. Формат данных

Файл `dataset.jsonl`, каждая строка — JSON объект:

```json
{"instruction": "...", "context": "...", "output": "..."}
```

Поля:
- `instruction` — описание проблемы от пользователя (или вопрос диагноста)
- `context` — дополнительная информация (логи, показания, модель оборудования)
- `output` — правильный ответ: диагноз + шаги решения

### 3.2. Примеры записей

```json
{"instruction": "У абонента нет интернета. Wi-Fi включён, кабель подключён. PPPoE не устанавливается.", "context": "Оборудование: ONT Huawei HG8245H. Порт OLT: 1/1/2. VLAN: 100.", "output": "Диагностика:\n1. Проверить статус PPPoE сессии на BRAS — сессия не установлена\n2. Проверить VLAN на порту OLT — VLAN 100 активен\n3. Проверить MAC-адрес ONT в таблице — MAC не обнаружен\n4. Вывод: ONT не прошёл аутентификацию. Решение: перезагрузить ONT, при повторе — замена оборудования"}
{"instruction": "Скорость интернета очень низкая — 2 Мбит/с вместо 100.", "context": "Тариф: 100 Мбит/с. Оборудование: TP-Link Archer C6. Подключение по Wi-Fi 5 ГГц.", "output": "Диагностика:\n1. Проверить скорость на кабеле — 95 Мбит/с (норма)\n2. Проверить скорость по Wi-Fi вблизи роутера — 80 Мбит/с\n3. Проверить скорость в другой комнате — 2 Мбит/с\n4. Вывод: проблема с покрытием Wi-Fi. Решение: рекомендовать Wi-Fi репитер или移-router в зону покрытия"}
{"instruction": "DNS не резолвится, сайты не открываются, но IP-адрес работает.", "context": "DNS сервер: 8.8.8.8. Роутер: Keenetic Viva.", "output": "Диагностика:\n1. Пинг 8.8.8.8 — работает\n2. Пинг by google.com — не резолвится\n3. Проверить DNS на роутере — указан 8.8.8.8\n4. Проверить DNS с ПК напрямую — работает\n5. Вывод: проблема с DNS-форвардингом на роутере. Решение: сбросить роутер, при повторе — перепрошить"}
{"instruction": "Абонент звонит: 'У меня всё пропало, ничего не работает'.", "context": "", "output": "Диагностика:\n1. Уточнить: что именно не работает (интернет, телевидение, телефон)\n2. Проверить статус абонента в биллинге — абонент активен\n3. Проверить порт на коммутаторе — порт в down\n4. Вывод: обрыв физического соединения. Решение: направить специалиста для проверки кабеля"}
{"instruction": "Телевидение пикирает, картинка разрывается.", "context": "IPTV:  multicast. Оборудование: STB Humax. Порт: 2/1/5.", "output": "Диагностика:\n1. Проверить IGMP snooping на свитче — включён\n2. Проверить трафик multicast на порту — превышает 30 Мбит/с\n3. Проверить количество multicast-групп — 15 (норма <10)\n4. Вывод: избыточное количество multicast-групп. Решение: оптимизировать конфигурацию IGMP, ограничить группы"}
```

### 3.3. Требования к данным

| Параметр | Минимум | Рекомендация |
|----------|---------|--------------|
| Количество записей | 1000 | 5000-15000 |
| Уникальность | Дедупликация по instruction | Разнообразные формулировки |
| Длина instruction | 10-500 токенов | Средняя ~50-100 токенов |
| Длина output | 50-500 токенов | Средняя ~100-200 токенов |
| Баланс классов | Минимум 50 записей на класс | Равномерное распределение |

### 3.4. Источники данных

1. **Тикетная система** — экспортировать историю обращений с решениями
2. **База знаний** — инструкции и чек-листы для операторов
3. **Руководства производителей** — документация по оборудованию (ONT, OLT, свитчи)
4. **Генерация с LLM** — использовать GPT-4/Claude для генерации синтетических примеров, затем верифицировать вручную

### 3.5. Скрипт валидации

```python
#!/usr/bin/env python3
"""validate_dataset.py — проверка качества датасета для fine-tuning"""

import json
import sys
from collections import Counter
from pathlib import Path


def validate(path: str) -> dict:
    errors = []
    warnings = []
    stats = {"total": 0, "fields_ok": 0, "duplicates": 0, "too_long": 0, "too_short": 0}

    instructions = []
    outputs = []

    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            stats["total"] += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"Строка {i}: невалидный JSON")
                continue

            required = {"instruction", "output"}
            if not required.issubset(row.keys()):
                missing = required - set(row.keys())
                errors.append(f"Строка {i}: отсутствуют поля {missing}")
                continue

            stats["fields_ok"] += 1
            inst = row["instruction"].strip()
            out = row["output"].strip()

            if len(inst) < 10:
                stats["too_short"] += 1
                warnings.append(f"Строка {i}: instruction слишком короткий ({len(inst)} символов)")

            if len(inst) > 2000:
                stats["too_long"] += 1
                warnings.append(f"Строка {i}: instruction слишком длинный ({len(inst)} символов)")

            if len(out) < 20:
                warnings.append(f"Строка {i}: output слишком короткий ({len(out)} символов)")

            instructions.append(inst)
            outputs.append(out)

    unique_inst = set(instructions)
    stats["duplicates"] = stats["total"] - len(unique_inst)

    # Подсчёт баланса классов (по ключевым словам)
    class_keywords = [
        "нет интернета", "скорость", "dns", "iptv", "telephon",
        "не работает", "обрыв", "блокировка", "роутер", "wi-fi"
    ]
    class_counts = Counter()
    for inst in instructions:
        inst_lower = inst.lower()
        matched = False
        for kw in class_keywords:
            if kw in inst_lower:
                class_counts[kw] += 1
                matched = True
                break
        if not matched:
            class_counts["другое"] += 1

    return {
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
        "class_distribution": dict(class_counts),
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "dataset.jsonl"
    result = validate(path)

    print(f"\n=== Валидация {path} ===")
    print(f"Всего записей: {result['stats']['total']}")
    print(f"Валидных полей: {result['stats']['fields_ok']}")
    print(f"Дубликатов: {result['stats']['duplicates']}")
    print(f"Слишком коротких instruction: {result['stats']['too_short']}")
    print(f"Слишком длинных instruction: {result['stats']['too_long']}")

    print(f"\n--- Распределение по классам ---")
    for cls, count in sorted(result["class_distribution"].items(), key=lambda x: -x[1]):
        print(f"  {cls}: {count}")

    if result["errors"]:
        print(f"\n--- Ошибки ({len(result['errors'])}) ---")
        for e in result["errors"][:10]:
            print(f"  {e}")
        sys.exit(1)

    if result["warnings"]:
        print(f"\n--- Предупреждения ({len(result['warnings'])}) ---")
        for w in result["warnings"][:10]:
            print(f"  {w}")

    print("\nOK")
```

Запуск:
```bash
python validate_dataset.py dataset.jsonl
```

---

## 4. Окружение и зависимости

### 4.1. Установка

```bash
# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Зависимости
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install transformers>=4.44.0
pip install peft>=0.12.0
pip install trl>=0.9.0
pip install datasets>=2.20.0
pip install bitsandbytes>=0.43.0
pip install accelerate>=0.33.0
pip install scipy
pip install sentencepiece
pip install protobuf
```

### 4.2. Проверка GPU

```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"Memory: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB")
```

---

## 5. Конфигурация обучения

### 5.1. Конфигурация QLoRA

```python
from peft import LoraConfig, TaskType

lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,                          # ранг — 16 оптимально для 7B
    lora_alpha=32,                 # scaling = 2 * r
    target_modules=[               # какие слои дообучаем
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ],
    lora_dropout=0.05,
    bias="none",
    modules_to_save=None,          # не замораживаем additional modules
)
```

**Пояснение параметров:**
- `r=16`: баланс между качеством и размером адаптера (~100MB vs ~50MB при r=8)
- `target_modules`: расширенный список для лучшего захвата знаний
- `lora_alpha=32`: стандартное соотношение 2:1 с rank

### 5.2. Конфигурация квантизации (QLoRA)

```python
from transformers import BitsAndBytesConfig

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",           # NormalFloat4 — лучшая точность
    bnb_4bit_compute_dtype=torch.bfloat16,# вычисления в bfloat16
    bnb_4bit_use_double_quant=True,       # двойная квантизация — экономия памяти
)
```

### 5.3. Гиперпараметры

```python
from transformers import TrainingArguments

training_args = TrainingArguments(
    output_dir="./checkpoints",
    
    # Основные
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,      # эффективный batch = 16
    gradient_checkpointing=True,        # экономия памяти
    
    # Learning rate
    learning_rate=2e-4,                 # стандарт для QLoRA
    lr_scheduler_type="cosine",         # косинусный шедулер
    warmup_ratio=0.03,                  # 3% warmup (~300 шагов для 10K)
    weight_decay=0.01,
    
    # Формат
    fp16=False,
    bf16=True,                          # bfloat16 если GPU поддерживает
    
    # Логирование и чекпоинты
    logging_steps=10,
    eval_strategy="steps",
    eval_steps=100,
    save_steps=200,
    save_total_limit=3,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
    
    # Оптимизация
    optim="paged_adamw_8bit",           # 8-bit оптимизатор для QLoRA
    max_grad_norm=0.3,
    group_by_length=True,               # группировка по длине — быстрее
)
```

**Подбор hyperparameters:**

| Параметр | Значение | Если loss не падает | Если переобучение |
|----------|----------|---------------------|-------------------|
| `learning_rate` | 2e-4 | Увеличить до 5e-4 | Уменьшить до 5e-5 |
| `r` (ранг) | 16 | Увеличить до 32 | Уменьшить до 8 |
| `epochs` | 3 | Увеличить до 5 | Уменьшить до 2 |
| `batch_size` | 16 | Уменьшить до 8 | Увеличить до 32 |
| `dropout` | 0.05 | Уменьшить до 0.01 | Увеличить до 0.1 |

---

## 6. Запуск обучения

### 6.1. Полный скрипт обучения

```python
#!/usr/bin/env python3
"""train.py — дообучение Qwen 2.5 7B для диагностики ISP"""

import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer

# === Конфигурация ===
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
DATASET_PATH = "dataset.jsonl"
OUTPUT_DIR = "./checkpoints"
ADAPTER_DIR = "./lora-adapter"

# === 1. Загрузка токенизатора ===
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# === 2. Конфигурация квантизации ===
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

# === 3. Загрузка модели ===
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
    torch_dtype=torch.bfloat16,
)
model = prepare_model_for_kbit_training(model)

# === 4. Конфигурация LoRA ===
lora_config = LoraConfig(
    task_type=0,  # CAUSAL_LM
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.05,
    bias="none",
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# === 5. Загрузка данных ===
dataset = load_dataset("json", data_files={
    "train": DATASET_PATH,
}, split="train")

# Разделение 90/10
split = dataset.train_test_split(test_size=0.1, seed=42)

# === 6. Форматирование промптов ===
SYSTEM_PROMPT = (
    "Ты — эксперт по диагностике инцидентов технической поддержки интернет-провайдера. "
    "Анализируй описание проблемы, определяй причину и предлагай пошаговую диагностику."
)

def format_prompt(example):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": example["instruction"]},
    ]
    if example.get("context"):
        messages[1]["content"] += f"\n\nКонтекст: {example['context']}"
    messages.append({"role": "assistant", "content": example["output"]})
    
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    return {"text": text}

dataset_formatted = split.map(format_prompt, remove_columns=split["train"].column_names)

# === 7. Аргументы обучения ===
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    gradient_checkpointing=True,
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    weight_decay=0.01,
    fp16=False,
    bf16=True,
    logging_steps=10,
    eval_strategy="steps",
    eval_steps=100,
    save_steps=200,
    save_total_limit=3,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
    optim="paged_adamw_8bit",
    max_grad_norm=0.3,
    group_by_length=True,
    report_to="none",
)

# === 8. Трейнер ===
trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=dataset_formatted["train"],
    eval_dataset=dataset_formatted["test"],
    dataset_text_field="text",
    max_seq_length=2048,
    tokenizer=tokenizer,
    packing=True,               # упаковка коротких примеров — быстрее
)

# === 9. Обучение ===
trainer.train()

# === 10. Сохранение ===
model.save_pretrained(ADAPTER_DIR)
tokenizer.save_pretrained(ADAPTER_DIR)
print(f"Адаптер сохранён в {ADAPTER_DIR}")
```

### 6.2. Запуск

```bash
# Один GPU
python train.py

# Множество GPU (FSDP)
torchrun --nproc_per_node=2 train.py

# С мониторингом TensorBoard
tensorboard --logdir ./checkpoints
python train.py  # training_args уже включает tensorboard
```

### 6.3. Мониторинг

Следить за метриками во время обучения:
- **train_loss** — должен стабильно giảmать
- **eval_loss** — ключевая метрика; рост = переобучение
- **learning_rate** — косинусный график от 0 до 2e-4 и обратно

Красные флаги:
- eval_loss растёт после эпохи 2 → переобучение, уменьшить epochs
- train_loss не падает → learning_rate слишком низкий или данные плохие
- loss = NaN → learning_rate слишком высокий, уменьшить до 5e-5

---

## 7. Оценка качества

### 7.1. Автоматическая оценка

```python
#!/usr/bin/env python3
"""evaluate.py — оценка дообученной модели"""

import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
import numpy as np

# === Конфигурация ===
BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
ADAPTER_DIR = "./lora-adapter"
TEST_FILE = "test.jsonl"       # отдельный тестовый набор (не из train)
SYSTEM_PROMPT = (
    "Ты — эксперт по диагностике инцидентов технической поддержки интернет-провайдера. "
    "Анализируй описание проблемы, определяй причину и предлагай пошаговую диагностику."
)

# === Загрузка модели ===
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
)
model = PeftModel.from_pretrained(base_model, ADAPTER_DIR)
model.eval()

# === Загрузка тестовых данных ===
test_data = []
with open(TEST_FILE, "r", encoding="utf-8") as f:
    for line in f:
        test_data.append(json.loads(line))

# === Генерация ответов ===
results = []

for i, row in enumerate(test_data):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": row["instruction"]},
    ]
    if row.get("context"):
        messages[1]["content"] += f"\n\nКонтекст: {row['context']}"
    
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            temperature=0.1,         # низкая temperature для воспроизводимости
            do_sample=False,         # greedy decoding для оценки
        )
    
    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
    
    results.append({
        "instruction": row["instruction"],
        "expected": row["output"],
        "generated": response,
    })
    
    print(f"[{i+1}/{len(test_data)}] OK")

# === Сохранение результатов ===
with open("eval_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\nРезультаты сохранены в eval_results.json")
print(f"Всего примеров: {len(results)}")
```

### 7.2. Ручная оценка

Проверить на 20-30 тестовых примерах вручную. Критерии:

| Критерий | Описание | Проходной балл |
|----------|----------|----------------|
| Классификация | Модель верно определяет тип инцидента | >90% |
| Диагностика | Предлагает логичную цепочку шагов | >80% |
| Решение | Рекомендация корректна и применима | >85% |
| Язык | Ответ грамотный, без галлюцинаций | >95% |

### 7.3. Сравнение с базовой моделью

Запустить тот же набор вопросов на базовой модели (без fine-tuning) и сравнить:
- Базовая модель будет давать общие/абстрактные ответы
- Дообученная — специфичные для ISP, с конкретными шагами

---

## 8. Деплой

### 8.1. Слияние адаптера

```python
#!/usr/bin/env python3
"""merge_adapter.py — слияние LoRA-адаптера с базовой моделью"""

from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import torch

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
ADAPTER_DIR = "./lora-adapter"
MERGED_DIR = "./merged-model"

# Загрузка
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.bfloat16,
    device_map="cpu",               # на CPU для слияния
    trust_remote_code=True,
)

# Слияние
model = PeftModel.from_pretrained(base_model, ADAPTER_DIR)
merged_model = model.merge_and_unload()

# Сохранение
merged_model.save_pretrained(MERGED_DIR)
tokenizer.save_pretrained(MERGED_DIR)
print(f"Модель сохранена в {MERGED_DIR}")
```

### 8.2. Квантизация для деплоя

```bash
# ГГUF формат для llama.cpp
pip install llama-cpp-python

# Конвертация
python convert_hf_to_gguf.py ./merged-model --outfile isp-diag.gguf --outtype q4_k_m
```

### 8.3. Запуск инференса

```python
#!/usr/bin/env python3
"""inference.py — инференс дообученной модели"""

from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import torch

MODEL_DIR = "./merged-model"    # или "./lora-adapter" + базовая модель

tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_DIR,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True,
)

pipe = pipeline("text-generation", model=model, tokenizer=tokenizer, max_new_tokens=512)

SYSTEM_PROMPT = (
    "Ты — эксперт по диагностике инцидентов технической поддержки интернет-провайдера. "
    "Анализируй описание проблемы, определяй причину и предлагай пошаговую диагностику."
)

def diagnose(user_message: str, context: str = "") -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    if context:
        messages[1]["content"] += f"\n\nКонтекст: {context}"
    
    result = pipe(messages, return_full_text=False)
    return result[0]["generated_text"]


# Пример использования
if __name__ == "__main__":
    answer = diagnose(
        "У абонента нет интернета, PPPoE не поднимается",
        "Оборудование: ONT Huawei HG8245H"
    )
    print(answer)
```

### 8.4. Оптимизация инференса

| Метод | Ускорение | Потеря качества |
|-------|-----------|-----------------|
| `q4_k_m` квантизация | ~3x | Минимальная |
| `q8_0` квантизация | ~2x | Практически нулевая |
| vLLM сервер | ~5x (batching) | Нулевая |
| TensorRT-LLM | ~8x | Минимальная |

---

## 9. Чеклист

### Перед обучением
- [ ] Датасет содержит минимум 1000 записей
- [ ] Запущен `validate_dataset.py` — 0 ошибок
- [ ] Баланс классов проверен (минимум 50 записей на класс)
- [ ] Дубликаты удалены
- [ ] GPU доступен и проверен (`torch.cuda.isparable()`)
- [ ] Зависимости установлены

### Во время обучения
- [ ] train_loss стабильно падает
- [ ] eval_loss не растёт (или растёт минимально)
- [ ] NaN/Inf loss — нет
- [ ] Чекпоинты сохраняются
- [ ] Время обучения в пределах ожиданий

### После обучения
- [ ] Модель сохранена (адаптер или merged)
- [ ] Протестирована на 20-30 ручных примерах
- [ ] Сравнена с базовой моделью
- [ ] Инференс работает (через pipeline или llama.cpp)
- [ ] Латентность приемлемая (<2 сек на ответ)
- [ ] Галлюцинации отсутствуют или минимизированы

### Перед деплоем
- [ ] Адаптер слит с моделью (если нужно)
- [ ] Квантизация применена (если нужна)
- [ ] Тестовый запуск на реальных данных пройден
- [ ] Модель не выдаёт конфиденциальную информацию
- [ ] Документация по использованию написана

---

## Дополнительные ресурсы

- [PEFT документация](https://huggingface.co/docs/peft)
- [TRL документация](https://huggingface.co/docs/trl)
- [Qwen 2.5 модель](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct)
- [BitsAndBytes квантизация](https://huggingface.co/docs/bitsandbytes)
