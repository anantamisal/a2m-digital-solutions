# Backend Deployment Guide - $0 Cost

Deploy your FastAPI backend for **FREE** using one of these platforms.

---

## 🚀 Option 1: Render.com (Recommended - Easiest)

**Free Tier:** 750 hours/month, spins down after 15 min inactivity

### Steps:

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/a2m-digital-solutions.git
   git push -u origin main
   ```

2. **Deploy on Render**
   - Go to [render.com](https://render.com) → Sign up with GitHub
   - Click **"New +"** → **"Blueprint"**
   - Connect your repo → Render will detect `render.yaml`
   - Click **"Apply"**

3. **Set Environment Variables** (in Render Dashboard → Environment)
   ```
   SMTP_USERNAME=your-gmail@gmail.com
   SMTP_PASSWORD=your-16-char-app-password
   CORS_ORIGINS=["https://your-frontend-domain.com"]
   ```

4. **Get Your API URL**
   - After deploy: `https://a2m-digital-solutions-api.onrender.com`
   - Test: `https://your-api-url.onrender.com/health`

---

## 🚂 Option 2: Railway.app (Good Alternative)

**Free Tier:** $5 credit/month (enough for small apps)

### Steps:

1. **Install Railway CLI**
   ```bash
   npm install -g @railway/cli
   railway login
   ```

2. **Deploy**
   ```bash
   cd backend
   railway init
   railway up
   ```

3. **Set Variables** in Railway Dashboard
   - `SMTP_USERNAME`, `SMTP_PASSWORD`, `CORS_ORIGINS`, etc.

---

## 🪰 Option 3: Fly.io (Great Free Allowance)

**Free Tier:** 3 shared-cpu-1x VMs, 160GB monthly transfer

### Steps:

1. **Install flyctl**
   ```bash
   curl -L https://fly.io/install.sh | sh
   fly auth login
   ```

2. **Create & Deploy**
   ```bash
   cd backend
   fly launch --no-deploy
   fly deploy
   ```

3. **Set Secrets**
   ```bash
   fly secrets set SMTP_USERNAME=your@gmail.com SMTP_PASSWORD=your-password
   ```

---

## 🐳 Option 4: Google Cloud Run (Most Generous Free Tier)

**Free Tier:** 2M requests/month, 360M vCPU-seconds, 180K GiB-seconds

### Steps:

1. **Setup gcloud**
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

2. **Deploy**
   ```bash
   cd backend
   gcloud run deploy a2m-api --source . --region us-central1 --allow-unauthenticated
   ```

---

## 📧 Email Setup (Required for All)

### Gmail SMTP (Free, Easiest)

1. **Enable 2FA** on Google Account
2. **Generate App Password:**
   - Go to: https://myaccount.google.com/apppasswords
   - Select "Mail" → "Other" → Name it "A2M Backend"
   - Copy the **16-character password** (no spaces)
3. **Set in Environment:**
   ```
   EMAIL_PROVIDER=gmail
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your@gmail.com
   SMTP_PASSWORD=your16charapppassword
   FROM_EMAIL=info@a2mdigitalsolutions.com
   TO_EMAIL=info@a2mdigitalsolutions.com
   ```

### Brevo (Free 300 emails/day - Better Deliverability)

1. Sign up at [brevo.com](https://www.brevo.com/)
2. Get SMTP credentials from SMTP & API settings
3. Set:
   ```
   EMAIL_PROVIDER=brevo
   SMTP_HOST=smtp-relay.brevo.com
   SMTP_PORT=587
   SMTP_USERNAME=your-brevo-login
   SMTP_PASSWORD=your-brevo-smtp-key
   ```

### SendGrid (Free 100 emails/day)

1. Sign up at [sendgrid.com](https://sendgrid.com/)
2. Verify sender identity
3. Create API key with "Mail Send" permission
4. Set:
   ```
   EMAIL_PROVIDER=sendgrid
   SENDGRID_API_KEY=your-api-key
   SENDGRID_FROM_EMAIL=verified@yourdomain.com
   ```

---

## 🔧 Local Development

```bash
cd backend

# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and edit environment
cp .env.example .env
# Edit .env with your values

# 4. Run server
uvicorn main:app --reload --port 8000

# 5. Test
# Open http://localhost:8000/docs
# Open http://localhost:8000/health
```

---

## 🌐 Connect Frontend to Backend

### Update `script.js` (line 16):

```javascript
// Development
const API_BASE_URL = 'http://localhost:8000';

// Production - REPLACE WITH YOUR DEPLOYED URL
const API_BASE_URL = 'https://a2m-digital-solutions-api.onrender.com';
```

### Update CORS in Backend (`config.py` or env):

```python
# Add your frontend domain
CORS_ORIGINS = [
    "https://your-frontend-domain.com",
    "https://www.your-frontend-domain.com"
]
```

---

## ✅ Verify Deployment

1. **Health Check:** `GET https://your-api.com/health`
   ```json
   {
     "status": "healthy",
     "app_name": "A2M Digital Solutions API",
     "version": "1.0.0",
     "environment": "production"
   }
   ```

2. **Submit Test Inquiry:** `POST https://your-api.com/api/inquiries`
   ```json
   {
     "name": "Test User",
     "email": "test@example.com",
     "service": "web-development",
     "message": "Testing the API from deployment"
   }
   ```

3. **Check Email** - Should arrive at your `TO_EMAIL`

4. **View Inquiries:** `GET https://your-api.com/api/inquiries`

---

## 🔒 Production Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Set `DEBUG=false`
- [ ] Update `CORS_ORIGINS` with your actual frontend domain
- [ ] Use strong `SMTP_PASSWORD` (App Password, not regular password)
- [ ] Set up custom domain (optional)
- [ ] Enable HTTPS (automatic on Render/Railway/Fly/Cloud Run)
- [ ] Monitor logs for errors
- [ ] Set up uptime monitoring (UptimeRobot - free)

---

## 💰 Cost Summary

| Platform | Monthly Cost | Limits |
|----------|-------------|--------|
| **Render** | $0 | 750 hrs, spins down |
| **Railway** | $0* | $5 credit/month |
| **Fly.io** | $0 | 3 VMs, 160GB transfer |
| **Cloud Run** | $0 | 2M requests |
| **Email (Gmail)** | $0 | 500/day |
| **Email (Brevo)** | $0 | 300/day |
| **Database (SQLite)** | $0 | Local file |

*Railway free tier requires credit card verification

---

## 🆘 Troubleshooting

### "CORS Error"
- Add your frontend URL to `CORS_ORIGINS` in backend env
- Redeploy backend

### "Email Not Sending"
- Check logs: `render.com/logs` or `fly logs`
- Verify SMTP credentials
- Check spam folder
- For Gmail: Must use App Password, not regular password

### "Database Locked" (SQLite)
- SQLite doesn't handle concurrent writes well
- For production scale, upgrade to PostgreSQL (free on Render/Neon/Supabase)

### "Service Spins Down" (Render Free)
- First request after 15 min takes ~30s to wake up
- Normal behavior on free tier
- Upgrade to paid plan for always-on

---

## 📞 Support

- Render Docs: https://render.com/docs
- Railway Docs: https://docs.railway.app
- Fly.io Docs: https://fly.io/docs
- FastAPI Docs: https://fastapi.tiangolo.com