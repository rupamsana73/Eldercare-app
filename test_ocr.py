import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eldercare_project.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
import json

u, _ = User.objects.get_or_create(username='test_ocr_user')
c = Client()
c.force_login(u)

with open(r'C:\Users\Edge\Desktop\sample_prescription.png', 'rb') as f:
    resp = c.post('/prescription-reader/process/', {'image': f}, HTTP_HOST='127.0.0.1')

data = json.loads(resp.content)
print('OCR Available:', data.get('ocr_available'))
print('Extracted Text:', repr(data.get('extracted_text')))
