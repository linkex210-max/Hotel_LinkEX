import json
import os
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase, Client
from django.utils import timezone
import jwt
from django.conf import settings

from apps.users.models import User, UserPropertyScope, RefreshToken
from apps.users.permissions import create_tokens, JWTAuth
from apps.properties.models import Property, RoomType, Unit
from apps.bookings.models import Booking
from apps.bookings.services import BookingService
from apps.finance.models import Payment, Invoice, OwnerStatement


class RefreshTokenLifecycleAndExceptionHandlingTestCase(TestCase):
    """Issues 13 & 14: Refresh token rotation, reuse detection, revocation, and narrow exception handling."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="jwtuser@hotel.com",
            password="StrongPassword123!",
            role=User.Role.PROPERTY_MANAGER,
        )

    def test_refresh_token_rotation_and_reuse_detection(self):
        access1, refresh1 = create_tokens(self.user)

        # 1. Valid refresh rotates token and revokes old one
        res = self.client.post(
            "/api/users/refresh",
            data=json.dumps({"refresh_token": refresh1}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        refresh2 = res.json()["refresh_token"]
        self.assertNotEqual(refresh1, refresh2)

        # 2. Reusing refresh1 must fail (401) AND revoke refresh2 (reuse detection!)
        res_reuse = self.client.post(
            "/api/users/refresh",
            data=json.dumps({"refresh_token": refresh1}),
            content_type="application/json",
        )
        self.assertEqual(res_reuse.status_code, 401)

        res_victim = self.client.post(
            "/api/users/refresh",
            data=json.dumps({"refresh_token": refresh2}),
            content_type="application/json",
        )
        self.assertEqual(res_victim.status_code, 401, "Reuse detection must revoke downstream rotated tokens")

    def test_logout_revokes_refresh_token(self):
        _, refresh1 = create_tokens(self.user)
        res_out = self.client.post(
            "/api/users/logout",
            data=json.dumps({"refresh_token": refresh1}),
            content_type="application/json",
        )
        self.assertEqual(res_out.status_code, 200)

        res_refresh = self.client.post(
            "/api/users/refresh",
            data=json.dumps({"refresh_token": refresh1}),
            content_type="application/json",
        )
        self.assertEqual(res_refresh.status_code, 401)

    def test_password_change_and_deactivation_revoke_tokens(self):
        _, refresh1 = create_tokens(self.user)
        self.user.set_password("NewStrongPassword456!")
        self.user.save()

        res = self.client.post(
            "/api/users/refresh",
            data=json.dumps({"refresh_token": refresh1}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)

        _, refresh2 = create_tokens(self.user)
        self.user.is_active = False
        self.user.save()
        res2 = self.client.post(
            "/api/users/refresh",
            data=json.dumps({"refresh_token": refresh2}),
            content_type="application/json",
        )
        self.assertEqual(res2.status_code, 401)

    def test_expired_refresh_token_rejected(self):
        _, refresh1 = create_tokens(self.user)
        RefreshToken.objects.filter(user=self.user).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        res = self.client.post(
            "/api/users/refresh",
            data=json.dumps({"refresh_token": refresh1}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)

    def test_jwt_auth_does_not_swallow_database_error(self):
        """Issue 13: JWTAuth must handle PyJWTError cleanly but NOT swallow DatabaseError."""
        auth = JWTAuth()
        class DummyReq:
            pass
        self.assertIsNone(auth.authenticate(DummyReq(), "not.a.valid.jwt"))

        access, _ = create_tokens(self.user)
        with patch("apps.users.permissions.User.objects.filter", side_effect=DatabaseError("DB down")):
            with self.assertRaises(DatabaseError):
                auth.authenticate(DummyReq(), access)


class MultiTenantIDORAndFinancePermissionsTestCase(TestCase):
    """Issues 10, 11 & 12: Granular finance permissions, cross-tenant IDOR, and public endpoint limits."""

    def setUp(self):
        os.environ["ZATCA_SELLER_VAT_NUMBER"] = "300000000000003"
        cache.clear()
        self.client = Client()

        self.prop_a = Property.objects.create(name="Hotel Alpha", city="Riyadh", address="Addr A")
        self.prop_b = Property.objects.create(name="Hotel Beta", city="Jeddah", address="Addr B")

        self.rt_a = RoomType.objects.create(property=self.prop_a, name="Room A", base_price=Decimal("400.00"))
        self.rt_b = RoomType.objects.create(property=self.prop_b, name="Room B", base_price=Decimal("600.00"))

        self.unit_a = Unit.objects.create(property=self.prop_a, room_type=self.rt_a, unit_number="A101")
        self.unit_b = Unit.objects.create(property=self.prop_b, room_type=self.rt_b, unit_number="B201")

        self.guest_a = User.objects.create_user(email="guesta@hotel.com", password="Pass123!User", role=User.Role.GUEST)
        self.guest_b = User.objects.create_user(email="guestb@hotel.com", password="Pass123!User", role=User.Role.GUEST)

        self.manager_a = User.objects.create_user(email="mgra@hotel.com", password="Pass123!User", role=User.Role.PROPERTY_MANAGER)
        UserPropertyScope.objects.create(
            user=self.manager_a,
            property=self.prop_a,
            can_manage_bookings=True,
            can_manage_pricing=True,
            can_view_finance=True,
            can_record_payments=True,
            can_verify_payments=True,
            can_record_expenses=True,
            can_generate_statements=True,
            can_settle_statements=True,
            can_issue_invoices=True,
        )

        # Read-only finance viewer on Property A (Issue 10)
        self.viewer_a = User.objects.create_user(email="viewera@hotel.com", password="Pass123!User", role=User.Role.ACCOUNTANT)
        UserPropertyScope.objects.create(
            user=self.viewer_a,
            property=self.prop_a,
            can_manage_bookings=False,
            can_view_finance=True,
        )

        self.check_in = date.today() + timedelta(days=2)
        self.check_out = date.today() + timedelta(days=3)
        self.booking_b = BookingService.create_booking_atomic(
            {
                "room_type_id": self.rt_b.id,
                "guest_name": "Guest B",
                "guest_phone": "+966500000002",
                "check_in_date": self.check_in,
                "check_out_date": self.check_out,
            },
            user=self.guest_b,
        )
        self.booking_a = BookingService.create_booking_atomic(
            {
                "room_type_id": self.rt_a.id,
                "guest_name": "Guest A",
                "guest_phone": "+966500000001",
                "check_in_date": self.check_in,
                "check_out_date": self.check_out,
            },
            user=self.guest_a,
        )

    def _auth_headers(self, user: User) -> dict:
        access, _ = create_tokens(user)
        return {"HTTP_AUTHORIZATION": f"Bearer {access}"}

    def test_granular_finance_permissions_block_view_only_user(self):
        """Issue 10: User with only can_view_finance=True must get 403 on all financial write endpoints."""
        headers = self._auth_headers(self.viewer_a)

        # 1. Record payment -> 403
        res = self.client.post(
            "/api/finance/payments",
            data=json.dumps({"booking_id": self.booking_a.id, "amount": "100.00", "method": "CASH"}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(res.status_code, 403)

        # 2. Verify payment -> 403
        pay = Payment.objects.create(booking=self.booking_a, amount=Decimal("100.00"), method=Payment.PaymentMethod.CASH)
        res = self.client.post(f"/api/finance/payments/{pay.id}/verify", **headers)
        self.assertEqual(res.status_code, 403)

        # 3. Record expense -> 403
        res = self.client.post(
            "/api/finance/expenses",
            data=json.dumps({
                "property_id": self.prop_a.id,
                "title": "AC Repair",
                "category": "MAINTENANCE",
                "amount": "50.00",
                "date_incurred": date.today().isoformat(),
            }),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(res.status_code, 403)

        # 4. Generate owner statement -> 403
        res = self.client.post(
            f"/api/finance/statements/generate?property_id={self.prop_a.id}&start_date={date.today().isoformat()}&end_date={date.today().isoformat()}",
            **headers,
        )
        self.assertEqual(res.status_code, 403)

        # 5. Settle owner statement -> 403
        stmt = OwnerStatement.objects.create(
            property=self.prop_a, period_start=date.today(), period_end=date.today()
        )
        res = self.client.post(f"/api/finance/statements/{stmt.id}/settle", **headers)
        self.assertEqual(res.status_code, 403)

        # 6. Issue invoice -> 403
        self.booking_a.is_paid = True
        self.booking_a.save(update_fields=["is_paid"])
        res = self.client.post(
            "/api/finance/invoices/generate",
            data=json.dumps({"booking_id": self.booking_a.id, "invoice_type": "SIMPLIFIED", "buyer_vat_number": ""}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(res.status_code, 403)

        # 7. Viewing issued invoice IS allowed (200)
        from apps.finance.services import InvoiceService
        inv = InvoiceService.create_and_issue_for_booking(self.booking_a)
        res = self.client.get(f"/api/finance/invoices/{inv.invoice_number}", **headers)
        self.assertEqual(res.status_code, 200)

    def test_cross_tenant_idor_blocked_across_all_endpoints(self):
        """Issue 11: Manager A and Guest A cannot access or mutate Property B / Guest B resources."""
        mgr_a_headers = self._auth_headers(self.manager_a)
        guest_a_headers = self._auth_headers(self.guest_a)

        # 1. Guest A cannot cancel Guest B's booking
        res = self.client.post(f"/api/bookings/{self.booking_b.id}/cancel", **guest_a_headers)
        self.assertEqual(res.status_code, 403)

        # 2. Guest A cannot pay for Guest B's booking
        res = self.client.post(
            "/api/finance/payments",
            data=json.dumps({"booking_id": self.booking_b.id, "amount": "100.00", "method": "CARD"}),
            content_type="application/json",
            **guest_a_headers,
        )
        self.assertEqual(res.status_code, 403)

        # 3. Manager A cannot issue invoice for Property B booking
        res = self.client.post(
            "/api/finance/invoices/generate",
            data=json.dumps({"booking_id": self.booking_b.id, "invoice_type": "SIMPLIFIED", "buyer_vat_number": ""}),
            content_type="application/json",
            **mgr_a_headers,
        )
        self.assertEqual(res.status_code, 403)

        # 4. Manager A cannot list units or inventory of Property B
        res_units = self.client.get(f"/api/properties/{self.prop_b.id}/units", **mgr_a_headers)
        self.assertEqual(res_units.status_code, 403)

        res_inv = self.client.get(
            f"/api/properties/room-types/{self.rt_b.id}/inventory?start_date={self.check_in}&end_date={self.check_out}",
            **mgr_a_headers,
        )
        self.assertEqual(res_inv.status_code, 403)

        # 5. Manager A cannot assign Property B's unit to Booking A or manage Booking B
        res_assign_b = self.client.post(
            f"/api/bookings/{self.booking_b.id}/assign-room",
            data=json.dumps({"unit_id": self.unit_b.id}),
            content_type="application/json",
            **mgr_a_headers,
        )
        self.assertEqual(res_assign_b.status_code, 403)

        res_cross_unit = self.client.post(
            f"/api/bookings/{self.booking_a.id}/assign-room",
            data=json.dumps({"unit_id": self.unit_b.id}),
            content_type="application/json",
            **mgr_a_headers,
        )
        self.assertEqual(res_cross_unit.status_code, 400)

    def test_public_endpoints_pagination_and_rate_limiting(self):
        """Issue 12: Public endpoints support pagination and enforce rate limiting (429)."""
        res = self.client.get("/api/properties/?limit=1&offset=0")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 1)

        with patch("apps.properties.api.is_rate_limited", return_value=True):
            res_rl = self.client.get("/api/properties/")
            self.assertEqual(res_rl.status_code, 429)
