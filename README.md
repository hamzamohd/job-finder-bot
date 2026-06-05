# Job Finder Bot 🚀

Automated job scraper that searches for **Founder Associate** roles across UK, Berlin, Paris, and nearby locations. Sends detailed email notifications every hour via GitHub Actions (completely free and 24/7).

## Features

✅ **Automatic Hourly Scraping** - Runs every hour via GitHub Actions  
✅ **Multiple Job Sources** - Indeed, LinkedIn, AngelList, Crunchboard, Google Jobs, Welcome to the Jungle  
✅ **Smart Deduplication** - SQLite database prevents duplicate emails  
✅ **HTML Email Notifications** - Beautiful, detailed job listings sent to your inbox  
✅ **No Cost** - Uses free GitHub Actions, no paid APIs needed  
✅ **Timezone Aware** - Respects your IST timezone  

## ⚡ Quick Start (3 Steps)

### 1. Generate Gmail App Password
1. Go to https://myaccount.google.com/security
2. Enable **2-Step Verification** (if needed)
3. Go to **App passwords** → Select "Mail" and "Windows/Linux"
4. Copy the **16-character password**

### 2. Set GitHub Secrets
Go to: https://github.com/hamzamohd/job-finder-bot/settings/secrets/actions

Create 3 secrets:
- `EMAIL_SENDER` → `hamzazaman1598@gmail.com`
- `EMAIL_PASSWORD` → Your 16-char app password
- `EMAIL_RECIPIENT` → `md.hamza.work@gmail.com`

### 3. Test It
Go to **Actions** → **Job Finder Bot - Hourly Scraper** → **Run workflow**

Check your email in 5 minutes! ✉️

## How It Works

```
Every Hour (automatically):
├─ Scrape all job boards
├─ Filter for "Founder Associate" 
├─ Check database for duplicates
├─ Add new jobs
└─ Send email notification
```

## Database

Jobs are stored in `jobs_database.db`:
- Prevents duplicate notifications
- Tracks all found jobs
- Auto-syncs to GitHub

## Customization

Edit `scraper.py`:
- Change locations, salary filters, email format
- Modify job sources

Edit `.github/workflows/scraper.yml`:
- Change cron schedule (default: every hour)

## Troubleshooting

**Email not working?**
- Verify Gmail app password is exactly 16 characters
- Check GitHub Secrets are set
- Check Actions tab for error logs

**No jobs found?**
- Job board HTML may have changed
- Check Actions logs for details

**Want to stop it?**
- Disable workflow in GitHub Actions or delete `.github/workflows/scraper.yml`