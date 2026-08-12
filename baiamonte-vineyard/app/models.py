from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class BlockCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=140)
    area_ha: float | None = Field(default=None, ge=0)
    planted_year: int | None = Field(default=None, ge=1800, le=2200)
    vine_count: int | None = Field(default=None, ge=0)
    training_system: str | None = None
    soil_type: str | None = None
    irrigation_available: bool = False
    notes: str | None = None


class VarietyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    target_gdd: float | None = Field(default=None, ge=0)
    notes: str | None = None


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=220)
    category: str = Field(default="general", max_length=80)
    status: Literal["planned", "in_progress", "done", "cancelled"] = "planned"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    due_date: date | None = None
    block_id: str | None = None
    estimated_hours: float | None = Field(default=None, ge=0)
    notes: str | None = None


class TaskStatusUpdate(BaseModel):
    status: Literal["planned", "in_progress", "done", "cancelled"]


class ParcelMapUpdate(BaseModel):
    center_latitude: float | None = Field(default=None, ge=-90, le=90)
    center_longitude: float | None = Field(default=None, ge=-180, le=180)
    geometry_geojson: dict[str, Any] | None = None
    map_url: str | None = Field(default=None, max_length=700)


class ActivityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=220)
    activity_date: date
    end_date: date | None = None
    category: str = Field(default="general", max_length=80)
    status: Literal["planned", "done", "cancelled"] = "done"
    block_id: str | None = None
    labor_hours: float | None = Field(default=None, ge=0)
    worker_count: int | None = Field(default=None, ge=0)
    cost_eur: float | None = Field(default=None, ge=0)
    notes: str | None = None

    @model_validator(mode="after")
    def date_order(self):
        if self.end_date and self.end_date < self.activity_date:
            raise ValueError("end_date cannot be before activity_date")
        return self


class HarvestCreate(BaseModel):
    variety_id: str
    harvested_at: datetime
    lot_code: str | None = Field(default=None, max_length=100)
    block_id: str | None = None
    planned_date: date | None = None
    planned_kg: float | None = Field(default=None, ge=0)
    gross_kg: float | None = Field(default=None, ge=0)
    tare_kg: float | None = Field(default=None, ge=0)
    weight_kg: float | None = Field(default=None, ge=0)
    crate_count: int | None = Field(default=None, ge=0)
    fruit_temp_c: float | None = None
    destination: str | None = None
    brix: float | None = Field(default=None, ge=0)
    babo: float | None = Field(default=None, ge=0)
    ph: float | None = Field(default=None, ge=0, le=14)
    ta_g_l: float | None = Field(default=None, ge=0)
    condition_grade: str | None = Field(default=None, max_length=40)
    status: Literal["provisional", "ready", "in_progress", "received", "reconciled", "hold", "cancelled"] = "received"
    notes: str | None = None

    @model_validator(mode="after")
    def reconcile_scale_weight(self):
        if self.weight_kg is None and self.gross_kg is not None and self.tare_kg is not None:
            self.weight_kg = round(self.gross_kg - self.tare_kg, 2)
        if self.gross_kg is not None and self.tare_kg is not None and self.gross_kg < self.tare_kg:
            raise ValueError("Gross weight cannot be less than tare weight")
        if self.status in {"received", "reconciled"} and self.weight_kg is None:
            raise ValueError("Enter net weight, or gross and tare, for received fruit")
        return self


class LabResultCreate(BaseModel):
    analyte_code: str = Field(min_length=1, max_length=80)
    analyte_name: str = Field(min_length=1, max_length=160)
    numeric_value: float | None = None
    text_value: str | None = None
    unit: str | None = None

    @model_validator(mode="after")
    def value_present(self):
        if self.numeric_value is None and not self.text_value:
            raise ValueError("numeric_value or text_value is required")
        return self


class LabSampleCreate(BaseModel):
    sample_name: str = Field(min_length=1, max_length=180)
    sample_type: Literal["grape", "must", "wine", "soil", "water", "other"]
    lab_date: date
    sampled_at: datetime | None = None
    block_id: str | None = None
    variety_id: str | None = None
    wine_lot_id: str | None = None
    laboratory: str | None = None
    notes: str | None = None
    results: list[LabResultCreate] = Field(default_factory=list)


class WeatherObservationCreate(BaseModel):
    station_id: str | None = None
    station_external_id: str | None = None
    observed_at: datetime
    temp_c: float | None = None
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    pressure_hpa: float | None = None
    wind_kph: float | None = Field(default=None, ge=0)
    wind_gust_kph: float | None = Field(default=None, ge=0)
    rain_mm: float | None = Field(default=None, ge=0)
    solar_wm2: float | None = Field(default=None, ge=0)
    uv_index: float | None = Field(default=None, ge=0)
    leaf_wetness_pct: float | None = Field(default=None, ge=0, le=100)
    soil_moisture_pct: float | None = Field(default=None, ge=0, le=100)
    soil_temp_c: float | None = None


class FinancialDocumentCreate(BaseModel):
    document_type: Literal["sales_invoice", "purchase_invoice", "credit_note", "receipt", "other"]
    document_number: str = Field(min_length=1, max_length=100)
    document_date: date
    due_date: date | None = None
    party_name: str | None = Field(default=None, max_length=220)
    taxable_amount: float = Field(default=0, ge=0)
    vat_amount: float = Field(default=0, ge=0)
    withholding_tax: float = Field(default=0, ge=0)
    payment_status: Literal["unpaid", "part_paid", "paid", "not_applicable", "unknown"] = "unknown"
    notes: str | None = None


class CashTransactionCreate(BaseModel):
    account_name: str = Field(min_length=1, max_length=160)
    account_type: Literal["bank", "credit_card", "cash", "owner_clearing", "other"] = "bank"
    transaction_date: date
    description: str = Field(min_length=1)
    party_name: str | None = Field(default=None, max_length=220)
    transaction_type: Literal["customer_receipt", "supplier_payment", "owner_contribution", "owner_draw", "bank_fee", "tax", "transfer", "refund", "other"] = "other"
    amount_in: float = Field(default=0, ge=0)
    amount_out: float = Field(default=0, ge=0)
    notes: str | None = None

    @model_validator(mode="after")
    def one_cash_direction(self):
        if self.amount_in and self.amount_out:
            raise ValueError("A transaction cannot have both money in and money out")
        if not self.amount_in and not self.amount_out:
            raise ValueError("Enter either money in or money out")
        return self
