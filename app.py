from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent
CATALOG_PATH = Path(os.environ.get("CATALOG_PATH", str(BASE_DIR / "catalog.json")))
AI_API_KEY = os.environ.get("AI_API_KEY", "").strip()
AI_MODEL = os.environ.get("AI_MODEL", "gpt-4.1-mini").strip()
AI_API_URL = os.environ.get("AI_API_URL", "https://api.openai.com/v1/chat/completions").strip()
AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "30"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "20"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
CATEGORY_GUIDE = {
    "Сантехника": ["течет", "кран", "смеситель", "сифон", "унитаз", "засор", "вода", "под раковиной"],
    "Электрика": ["розетка", "выключатель", "автомат", "искрит", "свет", "люстра", "электрика"],
    "Мебель": ["шкаф", "кровать", "комод", "петли", "ящик", "собрать мебель", "перекосило"],
    "Крепления": ["повесить", "кронштейн", "телевизор", "карниз", "полка", "зеркало"],
    "Окна и двери": ["окно", "дверь", "ручка", "замок", "уплотнитель", "балкон"],
    "Бытовая техника": ["стиральная", "посудомоечная", "духовка", "варочная", "вытяжка", "подключить технику"],
    "Уход за домом": ["кондиционер", "радиатор", "чистка", "герметик", "обслуживание"],
    "Профилактика дома": ["осмотр", "проверка", "чек", "профилактика"],
}
FEW_SHOT_EXAMPLES = [
    {
        "query": "Течет под раковиной на кухне, капает после включения воды.",
        "reason": "Похоже, проблема может быть в сифоне, подводке или соединении под раковиной. Лучше временно не пользоваться узлом без необходимости и проверить, где именно появляется вода.",
        "clarifying_question": "Вода появляется сразу при открытии крана или уже после слива?",
        "service_names": ["Замена сифона", "Замена подводки воды", "Герметизация раковины"],
    },
    {
        "query": "Не работает розетка на кухне, иногда выбивает автомат.",
        "reason": "Похоже на проблему с розеткой или линией питания. Безопаснее пока не пользоваться этой точкой и не включать в нее нагрузку до проверки.",
        "clarifying_question": "Искрит сама розетка или автомат отключается без искрения?",
        "service_names": ["Диагностика электрики", "Ремонт розетки", "Замена автоматов в щитке"],
    },
    {
        "query": "Нужно повесить телевизор на стену и аккуратно подключить.",
        "reason": "Похоже на задачу по навеске телевизора с последующим подключением. Важно заранее понимать материал стены и место вывода кабелей.",
        "clarifying_question": "Кронштейн уже есть или его тоже нужно установить?",
        "service_names": ["Установка телевизора на кронштейн", "Подключение телевизора", "Настройка Smart TV"],
    },
    {
        "query": "Шкаф перекосило, дверцы плохо закрываются.",
        "reason": "Похоже на регулировку петель или ремонт мебельной фурнитуры. Лучше не нагружать шкаф, пока не станет понятна причина перекоса.",
        "clarifying_question": "Проблема только с дверцами или корпус тоже шатается?",
        "service_names": ["Регулировка дверей шкафа", "Регулировка петель", "Ремонт мебели"],
    },
]


class ServiceMatch(BaseModel):
    name: str
    category: str
    price_from: int
    unit: str | None = None
    reason: str


class DiagnoseResponse(BaseModel):
    source: str
    reason: str
    clarifying_question: str | None = None
    matches: list[ServiceMatch]


def repair_text(value: Any) -> Any:
    if isinstance(value, str):
        if "Р" in value or "С" in value:
            try:
                fixed = value.encode("cp1251").decode("utf-8")
                if fixed:
                    return fixed
            except UnicodeError:
                return value
        return value
    if isinstance(value, list):
        return [repair_text(item) for item in value]
    if isinstance(value, dict):
        return {repair_text(key): repair_text(item) for key, item in value.items()}
    return value


def load_catalog() -> list[dict[str, Any]]:
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return repair_text(raw)


CATALOG = load_catalog()
FLAT_CATALOG = [
    {
        **service,
        "category": group["category"],
    }
    for group in CATALOG
    for service in group["services"]
]
CATALOG_BY_NAME = {service["name"]: service for service in FLAT_CATALOG}
CATALOG_NAMES = [service["name"] for service in FLAT_CATALOG]


def build_matches(service_names: list[str], reason: str) -> list[ServiceMatch]:
    matches: list[ServiceMatch] = []
    seen: set[str] = set()
    for name in service_names:
        service = CATALOG_BY_NAME.get(name)
        if not service or name in seen:
            continue
        seen.add(name)
        matches.append(
            ServiceMatch(
                name=service["name"],
                category=service["category"],
                price_from=service["price_from"],
                unit=service.get("unit"),
                reason=reason,
            )
        )
    return matches


def extract_json_object(raw_text: str) -> dict[str, Any]:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in AI response.")
    return json.loads(raw_text[start : end + 1])


def category_guide_text() -> str:
    parts = []
    for category, hints in CATEGORY_GUIDE.items():
        parts.append(f"- {category}: {', '.join(hints)}")
    return "\n".join(parts)


def examples_text() -> str:
    blocks = []
    for item in FEW_SHOT_EXAMPLES:
        blocks.append(
            json.dumps(
                {
                    "query": item["query"],
                    "result": {
                        "reason": item["reason"],
                        "clarifying_question": item["clarifying_question"],
                        "service_names": item["service_names"],
                    },
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(blocks)


def build_messages(text: str, photo_bytes: bytes | None = None, content_type: str | None = None) -> list[dict[str, Any]]:
    system_prompt = (
        "Ты помощник сайта частного мастера по дому в Краснодаре.\n"
        "Твоя задача: по описанию бытовой проблемы подобрать 2-4 реальные услуги из переданного каталога.\n"
        "Отвечай спокойно, коротко, честно и по-человечески.\n"
        "Не ставь точный диагноз без осмотра.\n"
        "Не выдумывай поломки, бренды, детали и услуги.\n"
        "Если фото нерелевантно, плохое или недостаточно информативное, скажи об этом прямо и попроси другой ракурс.\n"
        "Если есть риск, советуй только безопасные действия: перекрыть воду, отключить питание, временно не пользоваться узлом.\n"
        "Не путай категории между собой. Особенно не путай сантехнику, электрику, мебель, окна и двери, навеску и бытовую технику.\n"
        "Выбирай только услуги из переданного каталога и возвращай названия без изменений.\n"
        "reason должен содержать:\n"
        "1. что это может быть\n"
        "2. что безопасно сделать прямо сейчас\n"
        "3. короткий ориентир по стоимости через формулировку 'Обычно такие работы начинаются от ... ₽'\n"
        "clarifying_question должен быть один, короткий и полезный.\n"
        "Если уверенности мало, лучше выбрать более общую диагностику или близкие услуги, чем уверенно ошибиться.\n"
        "Верни только JSON вида: "
        '{"reason":"...","clarifying_question":"...","service_names":["...","..."]}.'
    )
    user_text = (
        f"Каталог услуг: {json.dumps(CATALOG_NAMES, ensure_ascii=False)}\n"
        f"Подсказка по категориям:\n{category_guide_text()}\n"
        f"Примеры хороших ответов:\n{examples_text()}\n"
        f"Описание проблемы клиента: {text}"
    )
    if photo_bytes is None or not content_type:
        user_content: Any = user_text
    else:
        encoded_photo = base64.b64encode(photo_bytes).decode("ascii")
        user_content = [
            {"type": "text", "text": user_text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{content_type};base64,{encoded_photo}"},
            },
        ]
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def normalize_reason(reason: str, matches: list[ServiceMatch]) -> str:
    clean_reason = " ".join((reason or "").split())
    if not clean_reason:
        clean_reason = "Похоже, это один из подходящих вариантов по вашему описанию."
    if "Обычно такие работы начинаются от" not in clean_reason and matches:
        clean_reason = f"{clean_reason} Обычно такие работы начинаются от {matches[0].price_from} ₽."
    return clean_reason


def normalize_question(question: str | None) -> str | None:
    clean_question = " ".join((question or "").split())
    if not clean_question:
        return "Если удобно, уточните один важный момент по задаче или пришлите фото крупнее."
    return clean_question


def call_openai(text: str, photo_bytes: bytes | None = None, content_type: str | None = None) -> DiagnoseResponse:
    if not AI_API_KEY:
        raise HTTPException(status_code=500, detail="AI_API_KEY is not configured.")

    payload = {
        "model": AI_MODEL,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": build_messages(text, photo_bytes=photo_bytes, content_type=content_type),
    }
    req = request.Request(
        AI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AI_API_KEY}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=AI_TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=502, detail=f"OpenAI HTTP error: {detail}") from exc
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="OpenAI request failed.") from exc

    try:
        content = body["choices"][0]["message"]["content"]
        parsed = extract_json_object(content)
        service_names = [
            name for name in parsed.get("service_names", []) if isinstance(name, str) and name in CATALOG_BY_NAME
        ]
        if not service_names:
            raise HTTPException(status_code=502, detail="OpenAI returned no usable service names.")
        matches = build_matches(service_names, "Подходит по вашему описанию.")[:4]
        return DiagnoseResponse(
            source="external-ai",
            reason=normalize_reason(str(parsed.get("reason", "")), matches),
            clarifying_question=normalize_question(parsed.get("clarifying_question")),
            matches=matches,
        )
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Failed to parse OpenAI response.") from exc


async def read_upload_bytes(photo: UploadFile) -> bytes:
    if photo.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG, PNG or WEBP images are supported.")
    body = await photo.read()
    if not body:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f"Photo must be no larger than {MAX_UPLOAD_MB} MB.")
    return body


app = FastAPI(title="Mast OK External AI Relay")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "ai_configured": bool(AI_API_KEY),
        "catalog_services": len(FLAT_CATALOG),
    }


@app.post("/api/diagnose", response_model=DiagnoseResponse)
def diagnose(payload: dict[str, str]) -> DiagnoseResponse:
    text = (payload.get("text") or "").strip()
    if len(text) < 3:
        raise HTTPException(status_code=400, detail="Text is too short.")
    return call_openai(text)


@app.post("/api/diagnose-form", response_model=DiagnoseResponse)
async def diagnose_form(
    text: str = Form(default=""),
    photo: UploadFile | None = File(default=None),
) -> DiagnoseResponse:
    clean_text = text.strip()
    photo_bytes: bytes | None = None
    content_type: str | None = None
    if photo is not None:
        photo_bytes = await read_upload_bytes(photo)
        content_type = photo.content_type
    if len(clean_text) < 3 and photo_bytes is None:
        raise HTTPException(status_code=400, detail="Add text or photo.")
    return call_openai(
        clean_text or "Клиент отправил фото без текста. Нужно аккуратно определить вероятную категорию задачи.",
        photo_bytes=photo_bytes,
        content_type=content_type,
    )
