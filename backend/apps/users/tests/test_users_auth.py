from django.test import TestCase, Client
from apps.users.models import User, UserPropertyScope
from apps.users.permissions import create_tokens

class UsersAuthTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="testuser@linkex.com",
            password="StrongPassword123!",
            first_name="Test",
            last_name="User",
            role=User.Role.GUEST
        )
        self.superadmin = User.objects.create_superuser(
            email="admin@linkex.com",
            password="AdminPassword123!"
        )

    def test_login_and_token_refresh(self):
        """ISS-11: User logs in, gets access and refresh tokens, and refreshes successfully"""
        # Login
        response = self.client.post(
            "/api/users/login",
            data={"email": "testuser@linkex.com", "password": "StrongPassword123!"},
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)

        refresh_token = data["refresh_token"]

        # Call /refresh
        refresh_response = self.client.post(
            "/api/users/refresh",
            data={"refresh_token": refresh_token},
            content_type="application/json"
        )
        self.assertEqual(refresh_response.status_code, 200)
        refresh_data = refresh_response.json()
        self.assertIn("access_token", refresh_data)
        self.assertIn("refresh_token", refresh_data)

    def test_refresh_with_invalid_token_fails(self):
        response = self.client.post(
            "/api/users/refresh",
            data={"refresh_token": "invalid.jwt.token"},
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)

    def test_property_scope_unauthorized_returns_403(self):
        """ISS-12: Non-superadmin cannot assign property scope and gets HTTP 403"""
        access_token, _ = create_tokens(self.user)
        response = self.client.post(
            "/api/users/property-scope",
            data={"user_id": self.user.id, "property_id": 1},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}"
        )
        self.assertEqual(response.status_code, 403)
