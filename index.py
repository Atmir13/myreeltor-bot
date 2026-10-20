"""Yandex Cloud Function для сбора объявлений ads-api.ru."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request


logger = logging.getLogger(__name__)
ADS_API_URL = "https://ads-api.ru/main/api"


def handler(event, context):
    """Получить объявления в РФ и передать их на Amvera."""
    del context
    user = os.getenv("ADS_API_USER", "")
    token = os.getenv("ADS_API_TOKEN", "")
    ingest_url = os.getenv("INGEST_URL", "")
    ingest_api_key = os.getenv("INGEST_API_KEY", "")
    params = {
        "user": user,
        "token": token,
        "city": "Нальчик",
        "category_id": 2,
        "limit": 50,
        "page": 1,
    }
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{ADS_API_URL}?{query}", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
        if result.get("code") != 200:
            logger.error("ads-api.ru вернул ошибку: %s", result)
            return {"statusCode": 502, "body": "Ошибка ads-api.ru"}
        ads = result.get("data", [])
        if not ads:
            logger.warning("ads-api.ru вернул пустой список")
            return {"statusCode": 200, "body": "OK"}
        if not ingest_url:
            logger.error("Не задан INGEST_URL")
            return {"statusCode": 500, "body": "INGEST_URL не настроен"}
        body = json.dumps({"ads": ads}).encode("utf-8")
        ingest_request = urllib.request.Request(
            ingest_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": ingest_api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(ingest_request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
        logger.info("Передано объявлений: %d; ответ Amvera: %s", len(ads), response_body)
        return {"statusCode": 200, "body": "OK"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        logger.exception("Ошибка синхронизации ads-api.ru: %s", error)
        return {"statusCode": 502, "body": "Ошибка внешнего сервиса"}
