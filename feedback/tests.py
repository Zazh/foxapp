from django.core.cache import cache
from django.test import TestCase, Client
from django.urls import reverse

from .models import FeedbackRequest


class FeedbackSubmitTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse('feedback_submit')
        self.valid_data = {'name': 'Test User', 'phone': '+971501234567'}
        cache.clear()

    def test_valid_submission(self):
        resp = self.client.post(self.url, self.valid_data)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
        self.assertEqual(FeedbackRequest.objects.count(), 1)

    def test_missing_fields(self):
        resp = self.client.post(self.url, {'name': 'Test'})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(FeedbackRequest.objects.count(), 0)

    def test_honeypot_blocks_bot(self):
        data = {**self.valid_data, 'website': 'http://spam.com'}
        resp = self.client.post(self.url, data)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])  # fake success
        self.assertEqual(FeedbackRequest.objects.count(), 0)  # not saved

    def test_rate_limit(self):
        for i in range(3):
            resp = self.client.post(self.url, {
                'name': f'User {i}', 'phone': f'+97150000000{i}'
            })
            self.assertEqual(resp.status_code, 200)

        # 4th request should be rate limited
        resp = self.client.post(self.url, self.valid_data)
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(FeedbackRequest.objects.count(), 3)

    def test_duplicate_within_5_minutes(self):
        self.client.post(self.url, self.valid_data)
        self.assertEqual(FeedbackRequest.objects.count(), 1)

        # Same phone + IP within 5 minutes
        resp = self.client.post(self.url, self.valid_data)
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(FeedbackRequest.objects.count(), 1)

    def test_different_phone_allowed(self):
        self.client.post(self.url, self.valid_data)
        resp = self.client.post(self.url, {
            'name': 'Other User', 'phone': '+971509999999'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(FeedbackRequest.objects.count(), 2)
