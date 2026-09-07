from django.contrib.auth import get_user_model


class LoggedInMixin:
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(username='test-fisher')
        self.client.force_login(self.user)
