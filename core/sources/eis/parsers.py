"""Парсеры XML ЕИС для 9 ядровых типов документов.

Парсят по localname (без привязки к префиксу namespace — ns2/ns3/ns7 варьируется
между экспортами одной и той же схемы).

Каждый парсер принимает корневой Element (внутри архива) и возвращает:
- dict  — для плоских типов (notice, contract, complaint, ...)
- (dict, [items]) — если есть позиции (notice, contract)

Пустые значения → None. Парсер НЕ падает на отсутствующих полях.
"""
from __future__ import annotations

from typing import Any
from lxml import etree


def _local(elem) -> str:
    return etree.QName(elem).localname


def _find_direct(parent, name: str):
    if parent is None:
        return None
    for c in parent:
        if _local(c) == name:
            return c
    return None


def _path(parent, *names):
    """Спуск по цепочке прямых потомков."""
    cur = parent
    for name in names:
        cur = _find_direct(cur, name)
        if cur is None:
            return None
    return cur


def _find_any(parent, name: str):
    """Первый потомок (на любой глубине) с localname=name."""
    if parent is None:
        return None
    for e in parent.iter():
        if e is parent:
            continue
        if _local(e) == name:
            return e
    return None


def _text(elem, default=None) -> str | None:
    if elem is None or elem.text is None:
        return default
    t = elem.text.strip()
    return t if t else default


def _text_direct(parent, name: str, default=None):
    return _text(_find_direct(parent, name), default)


def _text_any(parent, name: str, default=None):
    return _text(_find_any(parent, name), default)


def _float(s):
    try:
        return float(s) if s not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _int(s):
    try:
        return int(s) if s not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _get_root_doc(xml_bytes: bytes) -> tuple[str, Any] | None:
    """Вернуть (doc_type, element) — имя корневого документа внутри <export>.
    Обычно структура: <export><epNotificationEF2020>...</epNotificationEF2020></export>"""
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return None
    # сам root = <export> (или прямо doc)
    if _local(root) == "export":
        for c in root:
            return _local(c), c
        return None
    return _local(root), root


# ============ ПАРСЕРЫ ============

def parse_notice(doc, region_hint: str | None = None) -> tuple[dict, list[dict]]:
    """Извещения: epNotificationEF2020 / EOK2020 / EZK2020 / EZT2020.

    Returns: (notice_row, [notice_items])
    """
    doc_type = _local(doc)
    common = _find_direct(doc, "commonInfo")
    resp = _find_direct(doc, "purchaseResponsibleInfo")
    org_info = _path(resp, "responsibleOrgInfo") if resp is not None else None

    placing_way = _find_any(common, "placingWay")
    etp = _find_any(common, "ETP")

    # maxPrice и procedureInfo лежат в разных подветках разных извещений —
    # ищем первое вхождение (обычно только одно на документ).
    max_price = _float(_text_any(doc, "maxPrice"))
    currency = _text_any(doc, "currency") or _text_any(_find_any(doc, "currency"), "code")
    # workaround: currency может быть complex { code / name } — тогда берём code
    curr_el = _find_any(doc, "currency")
    if curr_el is not None:
        code = _text_direct(curr_el, "code")
        if code:
            currency = code

    # procedure: startDT / endDT (приём заявок)
    start_dt = _text_any(doc, "startDT")
    end_dt = _text_any(doc, "endDT")

    # execution period
    exec_el = _find_any(doc, "executionPeriod") or _find_any(doc, "contractConditions")
    exec_start = _text_any(exec_el, "startDate") if exec_el is not None else None
    exec_end = _text_any(exec_el, "endDate") if exec_el is not None else None

    notice = {
        "reg_number": _text_direct(common, "purchaseNumber") if common is not None else None,
        "version": _int(_text_direct(doc, "versionNumber")),
        "doc_type": doc_type,
        "publish_date": _text_direct(common, "publishDTInEIS") if common is not None else None,
        "submit_start_dt": start_dt,
        "submit_end_dt": end_dt,
        "max_price": max_price,
        "currency": currency,
        "placing_way_code": _text_direct(placing_way, "code"),
        "placing_way_name": _text_direct(placing_way, "name"),
        "etp_code": _text_direct(etp, "code"),
        "etp_name": _text_direct(etp, "name"),
        "purchase_object": _text_direct(common, "purchaseObjectInfo") if common is not None else None,
        "customer_reg_num": _text_direct(org_info, "regNum"),
        "customer_inn": _text_direct(org_info, "INN"),
        "customer_kpp": _text_direct(org_info, "KPP"),
        "customer_name": _text_direct(org_info, "fullName"),
        "customer_region": region_hint,
        "exec_start_date": exec_start,
        "exec_end_date": exec_end,
    }

    items: list[dict] = []
    # Позиции — чаще в purchaseObjects/purchaseObject или lots/lot/purchaseObjects
    for po in doc.iter():
        if _local(po) != "purchaseObject":
            continue
        okpd2 = _find_direct(po, "OKPD2")
        ktru = _find_direct(po, "KTRU")
        okei = _find_direct(po, "OKEI")
        items.append({
            "index_num": len(items) + 1,
            "okpd2_code": _text_direct(okpd2, "code") if okpd2 is not None else None,
            "okpd2_name": _text_direct(okpd2, "name") if okpd2 is not None else None,
            "ktru_code": _text_direct(ktru, "code") if ktru is not None else None,
            "ktru_name": _text_direct(ktru, "name") if ktru is not None else None,
            "name": _text_direct(po, "name"),
            "price": _float(_text_direct(po, "price")),
            "quantity": _float(_text_direct(po, "quantity")),
            "okei_code": _text_direct(okei, "code") if okei is not None else None,
        })

    return notice, items


def parse_protocol_final(doc, region_hint: str | None = None) -> dict:
    """Итоговые протоколы epProtocol*Final.

    ВАЖНО: в подсистеме PRIZ протоколы публикуются БЕЗ ИНН/названий участников —
    это legal-особенность («PRIZ — подсистема без протоколов со сведениями об
    участниках»). Поэтому winner_inn/winner_name всегда NULL; для получения
    победителя надо джойнить на contracts по purchase_number.

    Из протокола достаём: purchase_number, кол-во заявок, финальную цену
    (finalPrice/lastPriceOffer.price у заявки с appRating=1).
    """
    doc_type = _local(doc)
    common = _find_direct(doc, "commonInfo")

    # Идентификатор — externalId (GUID), fallback на id.
    reg_number = _text_direct(doc, "externalId") or _text_direct(doc, "id")
    purchase_number = _text_direct(common, "purchaseNumber") if common is not None else None
    publish_date = _text_direct(common, "publishDTInEIS") if common is not None else None

    apps = [e for e in doc.iter() if _local(e) == "applicationInfo"]
    final_price = None

    for app in apps:
        rating = _text_any(app, "appRating")
        if rating != "1":
            continue
        # Ищем финальную цену победителя в порядке специфичности:
        # 1. <finalPrice> (EF2020 аукцион) — прямое поле заявки
        # 2. <lastPriceOffer><price> (EF2020 подача ценовых предложений)
        # 3. <costCriterionInfo><offer> (EOK2020 — ценовой критерий конкурса)
        # 4. <price> где-то рядом (EZK/EZT)
        fp = _text_any(app, "finalPrice")
        if not fp:
            lpo = _find_any(app, "lastPriceOffer")
            if lpo is not None:
                fp = _text_direct(lpo, "price")
        if not fp:
            cci = _find_any(app, "costCriterionInfo")
            if cci is not None:
                fp = _text_any(cci, "offer")
        if not fp:
            fp = _text_any(app, "price")
        final_price = _float(fp)
        break

    return {
        "reg_number": reg_number or f"NOID-{purchase_number}-{doc_type}",
        "purchase_number": purchase_number,
        "doc_type": doc_type,
        "publish_date": publish_date,
        "participants_count": len(apps) or None,
        "winner_inn": None,         # не публикуется в PRIZ — см. docstring
        "winner_name": None,
        "winner_is_individual": None,
        "final_price": final_price,
    }


def parse_contract(doc, region_hint: str | None = None) -> tuple[dict, list[dict]]:
    """RGK/contract."""
    reg_num = _text_direct(doc, "regNum") or _text_any(doc, "regNum")

    foundation = _find_direct(doc, "foundation")
    # Две ветки основания: order (торги) и singleCustomer (ед.поставщик)
    fcs_order = _find_any(foundation, "order") if foundation is not None else None
    placing_info = _find_any(foundation, "singleCustomer") if foundation is not None else None
    placing_reason = None
    if placing_info is not None:
        reason = _find_direct(placing_info, "reason")
        placing_reason = _text_direct(reason, "name") if reason is not None else None
    # Реестровый номер извещения — notificationNumber (при торгах) или purchaseCode (ед.поставщик)
    notification_number = _text_any(fcs_order, "notificationNumber") if fcs_order is not None else None

    customer = _find_direct(doc, "customer")
    price_info = _find_direct(doc, "priceInfo")
    advance = _find_direct(doc, "advancePaymentSum")
    exec_period = _find_direct(doc, "executionPeriod")

    # supplier — первый supplierInfo
    suppliers = _find_direct(doc, "suppliersInfo")
    supplier_info = _find_direct(suppliers, "supplierInfo") if suppliers is not None else None
    supplier_inn = None
    supplier_kpp = None
    supplier_name = None
    supplier_type = None
    if supplier_info is not None:
        for tag in ("legalEntityRF", "individualRF", "foreignOrganization", "IP", "ipWithoutINN"):
            se = _find_direct(supplier_info, tag)
            if se is not None:
                supplier_type = tag
                egrul = _find_direct(se, "EGRULInfo") or _find_direct(se, "EGRIPInfo") or se
                supplier_inn = _text_any(egrul, "INN")
                supplier_kpp = _text_any(egrul, "KPP")
                if tag.startswith("legal") or tag == "foreignOrganization":
                    supplier_name = _text_any(egrul, "fullName")
                else:
                    supplier_name = " ".join(filter(None, [
                        _text_any(egrul, "lastName"),
                        _text_any(egrul, "firstName"),
                        _text_any(egrul, "middleName"),
                    ])) or _text_any(egrul, "fullName")
                break

    # currency
    currency = None
    if price_info is not None:
        curr = _find_direct(price_info, "currency")
        currency = _text_direct(curr, "code") if curr is not None else None

    # plan-2020 number (связка с RPGZ)
    plan_2020 = _text_any(doc, "plan2020Number")

    contract = {
        "reg_num": reg_num,
        "purchase_number": notification_number or (_text_any(placing_info, "purchaseCode") if placing_info is not None else None),
        "publish_date": _text_direct(doc, "publishDate"),
        "sign_date": _text_direct(doc, "signDate"),
        "contract_price": _float(_text_direct(price_info, "price")) if price_info is not None else None,
        "currency": currency,
        "contract_subject": _text_direct(doc, "contractSubject"),
        "advance_percent": _float(_text_direct(advance, "sumInPercents")) if advance is not None else None,
        "exec_start_date": _text_direct(exec_period, "startDate") if exec_period is not None else None,
        "exec_end_date": _text_direct(exec_period, "endDate") if exec_period is not None else None,
        "customer_reg_num": _text_direct(customer, "regNum") if customer is not None else None,
        "customer_inn": _text_direct(customer, "inn") if customer is not None else None,
        "customer_kpp": _text_direct(customer, "kpp") if customer is not None else None,
        "customer_name": _text_direct(customer, "fullName") if customer is not None else None,
        "customer_region": region_hint,
        "supplier_inn": supplier_inn,
        "supplier_kpp": supplier_kpp,
        "supplier_name": supplier_name,
        "supplier_type": supplier_type,
        "placing_foundation": placing_reason,
        "plan_2020_number": plan_2020,
    }

    items: list[dict] = []
    products = _find_direct(doc, "products")
    if products is not None:
        for p in products:
            if _local(p) != "product":
                continue
            okpd2 = _find_direct(p, "OKPD2")
            ktru = _find_direct(p, "KTRU")
            okei = _find_direct(p, "OKEI")
            vat = _find_direct(p, "VATRateInfo")
            items.append({
                "index_num": _int(_text_direct(p, "indexNum")) or (len(items) + 1),
                "okpd2_code": _text_direct(okpd2, "code") if okpd2 is not None else None,
                "okpd2_name": _text_direct(okpd2, "name") if okpd2 is not None else None,
                "ktru_code": _text_direct(ktru, "code") if ktru is not None else None,
                "ktru_name": _text_direct(ktru, "name") if ktru is not None else None,
                "name": _text_direct(p, "name"),
                "price": _float(_text_direct(p, "price")),
                "quantity": _float(_text_direct(p, "quantity")),
                "sum_amount": _float(_text_direct(p, "sum")),
                "okei_code": _text_direct(okei, "code") if okei is not None else None,
                "vat_code": _text_any(vat, "VATCode") if vat is not None else None,
            })

    return contract, items


def parse_complaint(doc, region_hint: str | None = None) -> dict:
    common = _find_direct(doc, "commonInfo")
    ko = _find_direct(doc, "KOInfo")
    indicted = _find_direct(doc, "indicted")
    customer_el = _find_direct(indicted, "customer") if indicted is not None else None

    applicant = _find_direct(doc, "applicantNew")
    applicant_inn = None
    applicant_name = None
    applicant_type = None
    if applicant is not None:
        for tag in ("legalEntity", "individualPerson", "IP", "foreignOrganization"):
            se = _find_direct(applicant, tag)
            if se is not None:
                applicant_type = tag
                applicant_inn = _text_any(se, "INN")
                if tag == "legalEntity" or tag == "foreignOrganization":
                    applicant_name = _text_any(se, "fullName")
                else:
                    applicant_name = " ".join(filter(None, [
                        _text_any(se, "lastName"),
                        _text_any(se, "firstName"),
                        _text_any(se, "middleName"),
                    ])) or _text_any(se, "fullName")
                break

    purchase = _path(doc, "object", "purchase")
    appeal = _find_direct(doc, "appealActionInfo")

    return {
        "reg_number": _text_direct(common, "regNumber") if common is not None else None,
        "reg_date": _text_direct(common, "regDate") if common is not None else None,
        "publish_date": _text_any(_find_any(common, "printFormInfo"), "publishDate") if common is not None else None,
        "ko_name": _text_direct(ko, "fullName") if ko is not None else None,
        "ko_inn": _text_direct(ko, "INN") if ko is not None else None,
        "ko_region": _text_direct(ko, "address") if ko is not None else None,
        "customer_inn": _text_direct(customer_el, "INN") if customer_el is not None else None,
        "customer_name": _text_direct(customer_el, "fullName") if customer_el is not None else None,
        "applicant_inn": applicant_inn,
        "applicant_name": applicant_name,
        "applicant_type": applicant_type,
        "purchase_number": _text_direct(purchase, "purchaseNumber") if purchase is not None else None,
        "purchase_name": _text_direct(purchase, "purchaseName") if purchase is not None else None,
        "appeal_action_code": _text_direct(appeal, "code") if appeal is not None else None,
        "appeal_action_name": _text_direct(appeal, "shortName") if appeal is not None else _text_direct(appeal, "fullName") if appeal is not None else None,
        "text_summary": (_text_direct(doc, "text") or "")[:500] or None,
    }


def parse_refusal(doc, region_hint: str | None = None) -> dict:
    doc_type = _local(doc)
    # contractProcedureUnilateralRefusal vs parContractProcedureUnilateralRefusal
    initiator = "supplier" if doc_type.startswith("par") else "customer"

    common = _find_direct(doc, "commonInfo")
    contract_info = _find_direct(doc, "contractInfo") or _find_any(doc, "contract")
    contract_reg = _text_any(contract_info, "regNum")

    customer = _find_direct(doc, "customer") or _find_any(doc, "customer")
    supplier = _find_direct(doc, "supplier") or _find_any(doc, "supplier")

    supplier_inn = None
    supplier_name = None
    if supplier is not None:
        for tag in ("legalEntityRF", "individualRF", "foreignOrganization", "IP"):
            se = _find_direct(supplier, tag)
            if se is not None:
                egrul = _find_direct(se, "EGRULInfo") or _find_direct(se, "EGRIPInfo") or se
                supplier_inn = _text_any(egrul, "INN")
                supplier_name = _text_any(egrul, "fullName") or " ".join(filter(None, [
                    _text_any(egrul, "lastName"),
                    _text_any(egrul, "firstName"),
                ]))
                break
        if supplier_inn is None:
            supplier_inn = _text_any(supplier, "INN")
            supplier_name = _text_any(supplier, "fullName")

    return {
        "reg_number": _text_direct(common, "regNumber") if common is not None else _text_any(doc, "regNumber"),
        "publish_date": _text_any(doc, "publishDate") or _text_any(common, "publishDate") if common is not None else None,
        "initiator": initiator,
        "contract_reg_num": contract_reg,
        "customer_inn": _text_direct(customer, "INN") if customer is not None else None,
        "customer_name": _text_direct(customer, "fullName") if customer is not None else None,
        "supplier_inn": supplier_inn,
        "supplier_name": supplier_name,
        "reason_summary": (_text_any(doc, "reason") or _text_any(doc, "foundation") or "")[:500] or None,
    }


def parse_unfair_supplier(doc, region_hint: str | None = None) -> tuple[dict, list[dict]]:
    """RNP/unfairSupplier2022."""
    common = _find_direct(doc, "commonInfo")
    approve_org = _find_direct(doc, "approveOrgInfo")
    create_reason_info = _find_direct(doc, "createReasonInfo")
    supplier_info = _find_direct(doc, "unfairSupplierInfo")
    auto_ex = _find_direct(doc, "autoExDateInfo")

    sup_inn = None
    sup_kpp = None
    sup_name = None
    sup_short = None
    sup_type = None
    if supplier_info is not None:
        for tag in ("legalEntityRFInfo", "individualRFInfo", "foreignOrgInfo", "IPInfo"):
            se = _find_direct(supplier_info, tag)
            if se is not None:
                sup_type = tag.replace("Info", "")
                sup_inn = _text_direct(se, "INN")
                sup_kpp = _text_direct(se, "KPP")
                sup_name = _text_direct(se, "fullName")
                sup_short = _text_direct(se, "shortName")
                break

    row = {
        "reg_number": _text_direct(common, "regNumber") if common is not None else None,
        "version": _int(_text_direct(common, "versionNumber")) if common is not None else None,
        "publish_date": _text_direct(common, "publishDT") if common is not None else None,
        "first_version_date": _text_direct(common, "firstVersionPublishDT") if common is not None else None,
        "approve_org_name": _text_direct(approve_org, "fullName") if approve_org is not None else None,
        "create_reason": _text_direct(create_reason_info, "createReason") if create_reason_info is not None else None,
        "supplier_inn": sup_inn,
        "supplier_kpp": sup_kpp,
        "supplier_name": sup_name,
        "supplier_short_name": sup_short,
        "supplier_type": sup_type,
        "auto_exclude_date": _text_direct(auto_ex, "autoExDate") if auto_ex is not None else None,
    }

    founders: list[dict] = []
    if supplier_info is not None:
        for f in supplier_info:
            if _local(f) != "founders":
                continue
            role = _find_direct(f, "type")
            founders.append({
                "founder_inn": _text_direct(f, "INN"),
                "founder_name": _text_direct(f, "fullName"),
                "role_code": _text_direct(role, "code") if role is not None else None,
                "role_name": _text_direct(role, "name") if role is not None else None,
            })

    return row, founders


def parse_tender_plan(doc, region_hint: str | None = None) -> dict:
    """RPGZ/tenderPlan2020 — для MVP берём только метаданные, без позиций."""
    common = _find_direct(doc, "commonInfo")
    customer = _find_direct(doc, "customer") or _find_any(doc, "customer")

    total_amount = None
    # totalAmount или totalPublicAmount — варьируется
    for name in ("totalAmount", "totalPublicAmount", "totalVolume"):
        v = _float(_text_any(doc, name))
        if v is not None:
            total_amount = v
            break

    return {
        "plan_number": _text_any(common, "plan2020Number") if common is not None else _text_any(doc, "plan2020Number"),
        "publish_date": _text_any(common, "publishDate") if common is not None else _text_any(doc, "publishDate"),
        "customer_inn": _text_direct(customer, "INN") if customer is not None else None,
        "customer_name": _text_direct(customer, "fullName") if customer is not None else None,
        "customer_region": region_hint,
        "total_amount": total_amount,
    }


# ============ ДИСПЕТЧЕР ============

# Типы которые мы парсим и куда они идут
NOTICE_TYPES = {
    "epNotificationEF2020", "epNotificationEOK2020",
    "epNotificationEZK2020", "epNotificationEZT2020",
}
PROTOCOL_TYPES = {
    "epProtocolEF2020Final", "epProtocolEOK2020Final",
    "epProtocolEZK2020Final", "epProtocolEZT2020Final",
}
CONTRACT_TYPES = {"contract"}
COMPLAINT_TYPES = {"complaint"}
REFUSAL_TYPES = {"contractProcedureUnilateralRefusal", "parContractProcedureUnilateralRefusal"}
UNFAIR_TYPES = {"unfairSupplier2022"}
PLAN_TYPES = {"tenderPlan2020"}

ALL_PARSED_TYPES = (
    NOTICE_TYPES | PROTOCOL_TYPES | CONTRACT_TYPES |
    COMPLAINT_TYPES | REFUSAL_TYPES | UNFAIR_TYPES | PLAN_TYPES
)


def parse_xml(xml_bytes: bytes, region_hint: str | None = None) -> tuple[str, Any] | None:
    """Вернуть (category, data). category ∈ {notice, protocol, contract, complaint,
    refusal, unfair, plan} или None если тип не распознан / не парсим."""
    res = _get_root_doc(xml_bytes)
    if res is None:
        return None
    doc_type, doc = res
    try:
        if doc_type in NOTICE_TYPES:
            return "notice", parse_notice(doc, region_hint)
        if doc_type in PROTOCOL_TYPES:
            return "protocol", parse_protocol_final(doc, region_hint)
        if doc_type in CONTRACT_TYPES:
            return "contract", parse_contract(doc, region_hint)
        if doc_type in COMPLAINT_TYPES:
            return "complaint", parse_complaint(doc, region_hint)
        if doc_type in REFUSAL_TYPES:
            return "refusal", parse_refusal(doc, region_hint)
        if doc_type in UNFAIR_TYPES:
            return "unfair", parse_unfair_supplier(doc, region_hint)
        if doc_type in PLAN_TYPES:
            return "plan", parse_tender_plan(doc, region_hint)
    except Exception as e:
        raise RuntimeError(f"parse error in {doc_type}: {e}") from e
    return None
