# ElderCare Application - Deployment Guide

## Deployment to Render

This guide will walk you through deploying the ElderCare application to Render.

### Prerequisites

1. A GitHub account with this repository pushed
2. A Render account (https://render.com)
3. Basic knowledge of Git and GitHub

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Prepare for Render deployment"
git push origin main
```

### Step 2: Create Render Account and Connect GitHub

1. Go to https://render.com and sign up
2. Click "New" → "Web Service"
3. Select "Build and deploy from a Git repository"
4. Connect your GitHub account and select this repository

### Step 3: Configure Environment Variables

In the Render dashboard, set these environment variables:

```
DEBUG=False
SECRET_KEY=<generate-a-secure-random-key>
ALLOWED_HOSTS=<your-render-app-url>.onrender.com,localhost
```

Generate a secure SECRET_KEY using:
```python
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

### Step 4: Create PostgreSQL Database (Optional)

For production, create a PostgreSQL database:

1. In Render dashboard, click "New" → "PostgreSQL"
2. Fill in the database details
3. Copy the DATABASE_URL
4. In your web service settings, add: `DATABASE_URL=<postgres-url>`

### Step 5: Deploy

The deployment will automatically:
- Install dependencies from requirements.txt
- Run migrations
- Collect static files
- Start the Gunicorn server

Your app will be available at: `<your-app-name>.onrender.com`

### Troubleshooting

- **Check logs**: View logs in Render dashboard to identify issues
- **Database migrations fail**: Ensure DATABASE_URL is set correctly
- **Static files not showing**: Verify STATIC_ROOT and STATICFILES_STORAGE settings
- **Import errors**: Ensure all packages are in requirements.txt

### Development vs Production

- Development: Uses SQLite (db.sqlite3) - runs automatically with DEBUG=True
- Production (Render): Uses PostgreSQL - runs with DEBUG=False
