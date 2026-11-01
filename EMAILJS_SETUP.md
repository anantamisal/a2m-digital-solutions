# EmailJS Setup Guide for A2M Digital Solutions

Follow these steps to make the contact form send emails directly to your inbox.

## 📧 Step 1: Create EmailJS Account

1. Go to **[emailjs.com](https://www.emailjs.com/)** and sign up for a free account
2. Verify your email address

## 🔧 Step 2: Add Email Service

1. In EmailJS Dashboard, go to **Email Services** → **Add New Service**
2. Choose **Gmail** (or Outlook, Yahoo, etc.)
3. Connect your email account (e.g., `info@a2mdigitalsolutions.com`)
4. **Copy the Service ID** (looks like: `service_abc123`)

## 📝 Step 3: Create Email Template

1. Go to **Email Templates** → **Create New Template**
2. Design your email template using these variables:

### Template Example:
```
Subject: New Inquiry from {{from_name}} - {{service}}

Hello A2M Team,

You have a new project inquiry:

**From:** {{from_name}} ({{from_email}})
**Phone:** {{phone}}
**Service:** {{service}}
**Budget:** {{budget}}
**Timeline:** {{timeline}}

**Project Details:**
{{message}}

---
Reply directly to this email to respond to {{from_name}} ({{reply_to}})
```

3. **Important:** Set "To Email" to your receiving email (e.g., `info@a2mdigitalsolutions.com`)
4. **Important:** Set "Reply To" to `{{reply_to}}` so replies go to the client
5. **Copy the Template ID** (looks like: `template_xyz789`)

## 🔑 Step 4: Get Public Key

1. Go to **Account** → **API Keys**
2. **Copy the Public Key** (looks like: `user_abc123xyz`)

## ⚙️ Step 5: Update Your Code

Open `script.js` and replace the placeholder values at the top:

```javascript
const EMAILJS_CONFIG = {
    publicKey: 'user_abc123xyz',        // Your Public Key
    serviceId: 'service_abc123',        // Your Service ID
    templateId: 'template_xyz789'       // Your Template ID
};
```

## ✅ Step 6: Test

1. Open your website
2. Fill out the contact form
3. Submit
4. Check your email inbox!

## 📊 Free Tier Limits

| Plan | Emails/Month |
|------|--------------|
| Free | 200 |
| Personal | 1,000 |
| Professional | 10,000 |

## 🛠️ Troubleshooting

### "EmailJS is not defined"
- Make sure the EmailJS script loads before your script.js
- Check browser console for errors

### Emails not arriving
- Check spam/junk folder
- Verify "To Email" in template matches your email
- Check EmailJS dashboard → **Logs** for delivery status

### CORS errors
- EmailJS handles CORS automatically
- If issues persist, add your domain in EmailJS → **Account** → **Domains**

## 🔒 Security Notes

- **Public Key** is safe to expose in frontend code
- **Private Key** should NEVER be in frontend (not used here)
- EmailJS validates requests against your allowed domains

## 📱 Alternative: WhatsApp Integration

If you also want WhatsApp inquiries, add this to your contact section:

```html
<a href="https://wa.me/91XXXXXXXXXX?text=Hello%20A2M%20Digital%20Solutions%2C%20I%20have%20a%20project%20inquiry"
   class="btn btn-secondary"
   target="_blank">
   💬 Chat on WhatsApp
</a>
```

Replace `91XXXXXXXXXX` with your WhatsApp number (country code + number, no + or spaces).

---

**Need help?** Check [EmailJS Documentation](https://www.emailjs.com/docs/) or contact their support.