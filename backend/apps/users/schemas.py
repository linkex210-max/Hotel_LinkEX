from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class TokenOutSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshTokenSchema(BaseModel):
    refresh_token: str

class UserCreateSchema(BaseModel):
    email: EmailStr
    password: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    phone_number: Optional[str] = None

class UserOutSchema(BaseModel):
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    phone_number: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class PermissionUpdateSchema(BaseModel):
    user_id: int
    property_id: int
    can_manage_bookings: bool = True
    can_manage_pricing: bool = False
    can_view_finance: bool = False
    can_record_payments: bool = False
    can_verify_payments: bool = False
    can_record_expenses: bool = False
    can_generate_statements: bool = False
    can_settle_statements: bool = False
    can_issue_invoices: bool = False
