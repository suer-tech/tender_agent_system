"""Клиент документо-информационного сервиса ЕИС (ДИС, zakupki.gov.ru).

Заменил мёртвый FTP с 01.01.2025. SOAP-интерфейс по токену.

Регистрация: https://zakupki.gov.ru/pmd/auth/welcome → Госуслуги → «потребитель
машиночитаемых данных». Токен класть в .env как EIS_DIS_TOKEN. Доступ с РФ-IP
(см. utils.vpn).

Сборка envelope — через zeep по WSDL. XSD использует `elementFormDefault=unqualified`,
поэтому ручной клиент не работал (см. project_eis_dis.md, коды ошибок #28/#24/#34).
"""
from __future__ import annotations

import os
import time
import uuid
from lxml import etree
from zeep import Client
from zeep.plugins import HistoryPlugin
from zeep.exceptions import Error as ZeepError

from .rate import TokenBucket

ENDPOINT = "https://int.zakupki.gov.ru/eis-integration/services/getDocsIP"
WSDL = ENDPOINT + "?wsdl"
NS_WS44 = "http://zakupki.gov.ru/fz44/get-docs-ip/ws"

# ДИС: 90 req/60s на токен (проверено 2026-04-21). Сверх — errorInfo code=13.
DIS_RATE_N = 90
DIS_RATE_WINDOW = 60.0
DIS_RATE_RETRY_PAUSE = 65.0  # пауза после code=13 — переждать окно

# Коды ошибок, требующие ретрая (не бросать EisDisError, а подождать и повторить).
RETRYABLE_CODES = {"13"}


class EisDisError(RuntimeError):
    pass


class EisDisRateError(EisDisError):
    """Rate limit (code=13) — ретраится автоматически клиентом."""


class EisDisClient:
    """SOAP-клиент ДИС поверх zeep.

    WSDL возвращает только 44-ФЗ (`fz44` namespace). Для 223-ФЗ на общем
    endpoint сервис возвращает echo запроса — требует другого канала (вероятно
    int223.zakupki.gov.ru + ГОСТ-TLS), пока не реализовано.
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        timeout: int = 60,
        rate_limiter: TokenBucket | None = None,
        max_retries: int = 3,
    ):
        self.token = token or os.getenv("EIS_DIS_TOKEN")
        if not self.token:
            raise EisDisError(
                "EIS_DIS_TOKEN не задан. Получи на "
                "https://zakupki.gov.ru/pmd/auth/welcome и положи в .env."
            )
        self._history = HistoryPlugin()
        try:
            self._client = Client(WSDL, plugins=[self._history])
        except ZeepError as e:
            raise EisDisError(f"Не удалось загрузить WSDL {WSDL}: {e}") from e
        self._client.transport.operation_timeout = timeout
        self._client.transport.load_timeout = timeout
        self._rate = rate_limiter if rate_limiter is not None else TokenBucket(DIS_RATE_N, DIS_RATE_WINDOW)
        self._max_retries = max_retries

    def get_docs_by_org_region(
        self,
        *,
        fz: str,
        region_code: str,
        subsystem: str,
        doc_type: str,
        exact_date: str,
    ) -> dict:
        """Запрос списка архивов по (регион × тип документа × дата).

        Args:
            fz: "44" (пока поддерживается только 44-ФЗ — см. docstring класса).
            region_code: код региона (напр. "77" — Москва).
            subsystem: PRIZ / RGK / RPP / RD223 / RI223 / ... (enum из XSD).
            doc_type: значение documentType из справочника nsiDocumentTypes.
            exact_date: YYYY-MM-DD.

        Returns:
            {"archive_urls": [str, ...], "raw_xml": bytes, "request_id": str}
        """
        if fz not in ("44", "223"):
            raise EisDisError(f"Неизвестный fz={fz}; ожидается 44 или 223")
        if fz == "223":
            raise EisDisError(
                "223-ФЗ на int.zakupki.gov.ru возвращает echo — нужен отдельный "
                "канал (int223 + ГОСТ-TLS). Пока не реализовано."
            )

        from datetime import datetime as _dt, timezone as _tz, date as _date

        request_id = str(uuid.uuid4())
        index = {
            "id": request_id,
            "createDateTime": _dt.now(_tz.utc).replace(microsecond=0),
            "mode": "PROD",
        }
        selection = {
            "orgRegion": region_code,
            "subsystemType": subsystem,
            f"documentType{fz}": doc_type,
            "periodInfo": {"exactDate": _date.fromisoformat(exact_date)},
        }
        header = etree.Element(f"{{{NS_WS44}}}individualPerson_token")
        header.text = self.token

        for attempt in range(self._max_retries + 1):
            self._rate.acquire()
            try:
                resp = self._client.service.getDocsByOrgRegion(
                    index=index, selectionParams=selection, _soapheaders=[header]
                )
            except ZeepError as e:
                raise EisDisError(f"SOAP error: {e}") from e

            raw_xml = b""
            if self._history.last_received:
                raw_xml = etree.tostring(self._history.last_received["envelope"])

            err = getattr(resp.dataInfo, "errorInfo", None) if getattr(resp, "dataInfo", None) else None
            if err is not None:
                code = str(err.code)
                if code in RETRYABLE_CODES and attempt < self._max_retries:
                    self._rate.pause(DIS_RATE_RETRY_PAUSE)
                    continue
                raise EisDisError(f"ДИС вернул errorInfo code={code}: {err.message}")

            urls = list(getattr(resp.dataInfo, "archiveUrl", None) or [])
            return {"archive_urls": urls, "raw_xml": raw_xml, "request_id": request_id}

        raise EisDisRateError(f"Превышен лимит после {self._max_retries} ретраев (code=13)")

    def download_archive(self, url: str) -> bytes:
        """Скачать архив по URL. При скачивании токен тоже нужен в заголовках."""
        sess = self._client.transport.session
        r = sess.get(url, headers={"individualPerson_token": self.token}, timeout=120)
        r.raise_for_status()
        return r.content
