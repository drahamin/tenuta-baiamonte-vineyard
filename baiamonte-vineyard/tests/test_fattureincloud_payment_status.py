from decimal import Decimal

from app.fattureincloud import _paid_amount, _payment_status


def test_reversed_received_document_payment_is_settled():
    document = {
        "entity": {"name": "Amazon EU S.a r.l., Succursale Italiana"},
        "payments_list": [
            {
                "amount": 66.49,
                "due_date": "2026-08-27",
                "paid_date": None,
                "status": "reversed",
            }
        ],
    }

    assert _payment_status(document) == "paid"
    assert _paid_amount(document) == Decimal("66.49")


def test_mixed_settled_and_unpaid_installments_are_part_paid():
    document = {
        "payments_list": [
            {"amount": 55.01, "status": "reversed"},
            {"amount": 20, "status": "not_paid"},
        ]
    }

    assert _payment_status(document) == "part_paid"
    assert _paid_amount(document) == Decimal("55.01")

