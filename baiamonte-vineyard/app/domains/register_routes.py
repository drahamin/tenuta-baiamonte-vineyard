from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..access import authorize_admin, authorize_register, request_username
from ..fattureincloud import pull_register_products
from .register import (
    capture_paypal_order, complete_cash_sale, complete_paypal_pos_sale, create_paypal_order, create_sale, dashboard,
    ledger, record_print, refresh_exchange_rate, sale, save_manual_catalog_item, save_register_settings,
    update_catalog_item, update_sale_payment, void_sale,
)


router = APIRouter(prefix="/api/v1/register", dependencies=[Depends(authorize_register)])


@router.get("/dashboard")
def register_dashboard(month: str | None = None) -> dict[str, Any]:
    return dashboard(month)


@router.post("/sales")
def new_sale(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return create_sale(payload, request_username(request))


@router.get("/sales/{sale_id}")
def get_sale(sale_id: str) -> dict[str, Any]:
    return sale(sale_id)


@router.post("/sales/{sale_id}/cash")
def pay_cash(sale_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return complete_cash_sale(sale_id, request_username(request), payload)


@router.post("/sales/{sale_id}/paypal-pos")
def pay_paypal_pos(sale_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return complete_paypal_pos_sale(sale_id, str(payload.get("reference") or ""), request_username(request))


@router.post("/sales/{sale_id}/paypal/order")
def paypal_order(sale_id: str, request: Request) -> dict[str, Any]:
    return create_paypal_order(sale_id, request_username(request))


@router.post("/sales/{sale_id}/paypal/capture")
def paypal_capture(sale_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return capture_paypal_order(sale_id, str(payload.get("order_id") or ""), request_username(request))


@router.put("/sales/{sale_id}", dependencies=[Depends(authorize_admin)])
def correct_sale_payment(sale_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return update_sale_payment(sale_id, payload, request_username(request))


@router.post("/sales/{sale_id}/void", dependencies=[Depends(authorize_admin)])
def cancel_sale(sale_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return void_sale(sale_id, request_username(request), str(payload.get("reason") or ""))


@router.post("/sales/{sale_id}/printed")
def printed_sale(sale_id: str, request: Request) -> dict[str, Any]:
    return record_print(sale_id, request_username(request))


@router.get("/ledger.csv")
def export_ledger(month: str | None = None) -> StreamingResponse:
    data = ledger(month)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Receipt", "Completed", "Status", "Payment", "PayPal account", "Language", "Payment reference", "Customer", "Subtotal EUR", "Discount EUR", "VAT EUR", "Total EUR", "Tender currency", "Tender total", "USD per EUR", "Items", "Created by", "FIC posting"])
    for row in data["sales"]:
        writer.writerow([row["receipt_number"], row.get("completed_at") or "", row["status"], row.get("payment_method") or "", row.get("paypal_account") or "", row.get("checkout_language") or "", row.get("terminal_reference") or row.get("paypal_capture_id") or "", row.get("customer_name") or "", row["subtotal_eur"], row["discount_eur"], row["vat_eur"], row["total_eur"], row["currency"], row["tender_total"], row.get("usd_per_eur") or "", row["item_quantity"], row["created_by"], "disabled · local ledger"])
    payload = buffer.getvalue().encode("utf-8-sig")
    return StreamingResponse(iter([payload]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="baiamonte-register-{data["month"]}.csv"'})


@router.post("/inventory/sync")
def sync_inventory() -> dict[str, Any]:
    return pull_register_products()


@router.post("/catalog/manual")
def create_manual_item(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_manual_catalog_item(payload, request_username(request))


@router.put("/catalog/{item_id}", dependencies=[Depends(authorize_admin)])
def change_catalog_item(item_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return update_catalog_item(item_id, payload, request_username(request))


@router.put("/settings", dependencies=[Depends(authorize_admin)])
def change_settings(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_register_settings(payload, request_username(request))


@router.post("/exchange-rate/refresh", dependencies=[Depends(authorize_admin)])
def update_exchange_rate(request: Request) -> dict[str, Any]:
    return refresh_exchange_rate(request_username(request))
