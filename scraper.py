import requests
import sqlite3
import json
from datetime import datetime, timedelta
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
from pytz import timezone
import hashlib
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Timezone setup
IST = timezone('Asia/Kolkata')

def get_ist_now():
    """Get current time in IST"""
    return datetime.now(IST)

# Database setup
DB_FILE = "jobs_database.db"

def init_db():
    """Initialize SQLite database to track seen jobs"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            job_hash TEXT UNIQUE,
            title TEXT,
            company TEXT,
            location TEXT,
            salary TEXT,
            url TEXT,
            description TEXT,
            source TEXT,
            found_date TIMESTAMP,
            notified INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def create_job_hash(title, company, location):
    """Create unique hash for job to detect duplicates"""
    key = f"{title}|{company}|{location}".lower().strip()
    return hashlib.md5(key.encode()).hexdigest()

def job_exists(job_hash):
    """Check if job already exists in database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM jobs WHERE job_hash = ?", (job_hash,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_job(job_hash, title, company, location, salary, url, description, source):
    """Add new job to database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO jobs (job_hash, title, company, location, salary, url, description, source, found_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (job_hash, title, company, location, salary, url, description, source, get_ist_now()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def is_first_run():
    """Check if this is the first run (database is empty)"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    count = cursor.fetchone()[0]
    conn.close()
    return count == 0

def get_recent_jobs(hours=1):
    """Get jobs found in the last N hours"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    time_threshold = get_ist_now() - timedelta(hours=hours)
    cursor.execute("""
        SELECT id, title, company, location, salary, url, description, source
        FROM jobs WHERE found_date > ? AND notified = 0
        ORDER BY found_date DESC
    """, (time_threshold,))
    jobs = cursor.fetchall()
    conn.close()
    return jobs

def mark_notified(job_ids):
    """Mark jobs as notified"""
    if not job_ids:
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(job_ids))
    cursor.execute(f"UPDATE jobs SET notified = 1 WHERE id IN ({placeholders})", job_ids)
    conn.commit()
    conn.close()

# Job scraping functions

def scrape_linkedin_jobs():
    """Scrape LinkedIn/Indeed jobs using multiple free APIs"""
    jobs = []

    try:
        print("Scraping LinkedIn/Indeed via free APIs...")

        # GitHub Jobs API (deprecated but still works)
        try:
            for keyword in ["Founder Associate", "Associate", "Founder"]:
                search_url = f"https://jobs.github.com/positions.json?description={keyword}"
                response = requests.get(search_url, timeout=5)

                if response.status_code == 200:
                    data = response.json()
                    for job in data:
                        location = job.get('location', '')
                        # Check if location matches our targets
                        if any(loc in location.lower() for loc in ['uk', 'london', 'berlin', 'paris', 'amsterdam', 'netherlands', 'germany', 'france']):
                            job_hash = create_job_hash(
                                job.get('title', ''),
                                job.get('company', ''),
                                location
                            )

                            if not job_exists(job_hash):
                                jobs.append({
                                    'job_hash': job_hash,
                                    'title': job.get('title', ''),
                                    'company': job.get('company', ''),
                                    'location': location,
                                    'salary': 'Not specified',
                                    'url': job.get('url', ''),
                                    'description': job.get('description', '')[:300],
                                    'source': 'GitHub Jobs'
                                })
        except Exception as e:
            pass

        # RemoteOK API - free jobs API
        try:
            search_url = "https://remoteok.io/api"
            response = requests.get(search_url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                for job in data:
                    if isinstance(job, dict):
                        location = job.get('location', '')
                        company = job.get('company', '')
                        title = job.get('title', '')

                        # Check location
                        if any(loc in location.lower() for loc in ['uk', 'london', 'berlin', 'paris', 'amsterdam', 'netherlands', 'germany', 'france']):
                            # Check if it's a founder/associate role
                            if any(role in title.lower() for role in ['founder', 'associate', 'co-founder']):
                                job_hash = create_job_hash(title, company, location)

                                if not job_exists(job_hash):
                                    jobs.append({
                                        'job_hash': job_hash,
                                        'title': title,
                                        'company': company,
                                        'location': location,
                                        'salary': 'Not specified',
                                        'url': job.get('url', ''),
                                        'description': job.get('description', '')[:300],
                                        'source': 'RemoteOK'
                                    })
        except Exception as e:
            pass

        if len(jobs) > 0:
            print(f"  Found {len(jobs)} jobs from free APIs")
        else:
            print(f"  Found 0 jobs")
    except Exception as e:
        print(f"Error with LinkedIn scraping: {e}")

    return jobs

def scrape_arbeitnow():
    """Scrape Arbeitnow API for EU jobs (free, no auth required)"""
    jobs = []
    keywords = ["Founder Associate", "Founder's Associate", "Associate", "Founder"]

    try:
        print("Scraping Arbeitnow API...")
        for keyword in keywords:
            try:
                # Arbeitnow API endpoint - try with different parameters
                url = "https://api.arbeitnow.com/api/v2/jobs"
                params = {
                    'search': keyword,
                    'page': 1,
                    'limit': 100
                }

                # Add custom headers to avoid being blocked
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }

                response = requests.get(url, params=params, timeout=10, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    for job in data.get('data', []):
                        # Check if location matches our targets
                        location_obj = job.get('location', {})
                        if isinstance(location_obj, dict):
                            city = location_obj.get('city', '')
                            country = location_obj.get('country', '')
                        else:
                            city = str(location_obj)
                            country = ''

                        location_str = f"{city}, {country}".strip(', ')

                        # Check if location or job title matches
                        if any(loc in location_str for loc in ['UK', 'Germany', 'France', 'Netherlands', 'England', 'London', 'Berlin', 'Paris', 'Amsterdam']):
                            job_hash = create_job_hash(
                                job.get('title', ''),
                                job.get('company', {}).get('name', '') if isinstance(job.get('company'), dict) else job.get('company', ''),
                                location_str
                            )

                            if not job_exists(job_hash):
                                jobs.append({
                                    'job_hash': job_hash,
                                    'title': job.get('title', ''),
                                    'company': job.get('company', {}).get('name', '') if isinstance(job.get('company'), dict) else job.get('company', ''),
                                    'location': location_str,
                                    'salary': job.get('salary', 'Not specified'),
                                    'url': job.get('url', ''),
                                    'description': job.get('description', '')[:300],
                                    'source': 'Arbeitnow'
                                })
            except Exception as e:
                # Continue to next keyword instead of failing
                continue

        print(f"  Found {len(jobs)} jobs")
    except Exception as e:
        print(f"Error scraping Arbeitnow: {e}")

    return jobs

def scrape_eures():
    """Scrape EURES EU job database"""
    jobs = []

    try:
        print("Scraping EURES API...")

        # Try multiple search keywords
        keywords = ['Founder Associate', 'Associate', 'Founder', 'Startup']

        for keyword in keywords:
            try:
                url = "https://eures.europa.eu/api/v2/jobs"
                params = {
                    'keywords': keyword,
                    'pagesize': 100,
                    'sortBy': 'date'
                }

                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    for job in data.get('results', []):
                        country = job.get('country', '')
                        if any(c in country for c in ['United Kingdom', 'Germany', 'France', 'Netherlands']):
                            job_title = job.get('jobTitle', '').lower()
                            # Check if it matches our criteria (founder + associate/related)
                            if 'founder' in job_title or 'associate' in job_title:
                                job_hash = create_job_hash(
                                    job.get('jobTitle', ''),
                                    job.get('company', ''),
                                    f"{job.get('city', '')}, {country}"
                                )

                                if not job_exists(job_hash):
                                    jobs.append({
                                        'job_hash': job_hash,
                                        'title': job.get('jobTitle', ''),
                                        'company': job.get('company', ''),
                                        'location': f"{job.get('city', '')}, {country}",
                                        'salary': job.get('salary', 'Not specified'),
                                        'url': job.get('jobUrl', ''),
                                        'description': job.get('jobDescription', '')[:300],
                                        'source': 'EURES'
                                    })
            except Exception as e:
                continue

        print(f"  Found {len(jobs)} jobs")
    except Exception as e:
        print(f"Error scraping EURES: {e}")

    return jobs

def scrape_apify_vc_jobs():
    """Scrape VC portfolio jobs using Apify API"""
    jobs = []
    api_token = os.getenv('APIFY_API_TOKEN', '')

    if not api_token:
        print("WARNING: APIFY_API_TOKEN not set. Skipping Apify VC jobs.")
        return jobs

    try:
        print("Scraping Apify VC Portfolio Jobs...")
        # Apify VC Portfolio Jobs Aggregator endpoint
        url = f"https://api.apify.com/v2/actor-tasks/parseforge~vc-portfolio-jobs-aggregator-scraper/runs"

        headers = {
            'Authorization': f'Bearer {api_token}'
        }

        # This would require proper Apify task setup
        # For now, we'll skip if not configured
        print("  Apify VC scraper requires task configuration")
    except Exception as e:
        print(f"Error with Apify: {e}")

    return jobs

def filter_jobs(jobs):
    """Filter jobs based on criteria"""
    filtered = []
    locations = ['uk', 'london', 'berlin', 'paris', 'amsterdam', 'netherlands', 'germany', 'france', 'united kingdom', 'europe', 'england']

    for job in jobs:
        title_lower = job['title'].lower()
        location_lower = job['location'].lower()

        # Check if it's a founder-related role (more flexible matching)
        # Match: "Founder Associate", "Founder's Associate", "Associate to Founder", etc.
        has_founder = 'founder' in title_lower or 'co-founder' in title_lower
        has_associate = 'associate' in title_lower or 'startup' in title_lower or 'venture' in title_lower

        is_founder_role = has_founder or (has_associate and ('founder' in job['company'].lower() if job['company'] else False))

        # If no strict match, be more lenient and check for relevant keywords
        if not is_founder_role:
            is_founder_role = (has_founder and ('associate' in title_lower or 'operations' in title_lower or 'relations' in title_lower or 'business' in title_lower))

        if not is_founder_role:
            continue

        # Check location match
        location_match = any(loc in location_lower for loc in locations)
        if not location_match:
            continue

        filtered.append(job)

    return filtered

def deduplicate_jobs(jobs):
    """Remove duplicates by checking title, company, location"""
    seen = {}
    unique = []

    for job in jobs:
        key = f"{job['title']}|{job['company']}|{job['location']}".lower().strip()
        if key not in seen:
            seen[key] = True
            unique.append(job)

    return unique

def send_email(recipient, jobs, no_jobs=False, search_hours=1):
    """Send HTML email with job listings"""
    sender = os.getenv('EMAIL_SENDER', 'job-finder-bot@gmail.com')
    password = os.getenv('EMAIL_PASSWORD', '')
    current_time = get_ist_now()
    next_scan_time = current_time + timedelta(hours=1)

    if not password:
        print("WARNING: EMAIL_PASSWORD not set. Email will not be sent.")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Job Finder Bot - {current_time.strftime('%Y-%m-%d %H:%M IST')}"
    msg['From'] = sender
    msg['To'] = recipient

    if no_jobs:
        html_content = f"""
        <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); margin: 0; padding: 20px; }}
                    .container {{ background: white; border-radius: 12px; max-width: 600px; margin: 0 auto; box-shadow: 0 4px 6px rgba(0,0,0,0.1); padding: 30px; }}
                    .header {{ text-align: center; margin-bottom: 30px; }}
                    .emoji {{ font-size: 48px; margin-bottom: 10px; }}
                    h1 {{ color: #333; margin: 0; font-size: 24px; }}
                    p {{ color: #666; line-height: 1.6; margin: 15px 0; }}
                    .next-scan {{ background: #f0f4ff; padding: 15px; border-radius: 8px; color: #667eea; font-size: 13px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="emoji">😴</div>
                        <h1>All Quiet</h1>
                    </div>
                    <p>No new <strong>Founder Associate</strong> roles found in UK, Berlin, Paris, or Amsterdam in the last {search_hours} hour{'s' if search_hours > 1 else ''}.</p>
                    <div class="next-scan">
                        ⏰ Next scan: {next_scan_time.strftime('%Y-%m-%d %H:%M IST')}
                    </div>
                </div>
            </body>
        </html>
        """
    else:
        job_rows = ""
        for idx, job in enumerate(jobs, 1):
            salary_display = job[4] if job[4] != 'Not specified' else '💰 Competitive'
            description_snippet = job[6][:150] + "..." if len(job[6]) > 150 else job[6]
            source = job[7]
            job_rows += f"""
            <div class="job-card">
                <div class="job-header">
                    <div class="job-number">#{idx}</div>
                    <div class="job-source">{source}</div>
                </div>
                <h3 class="job-title">{job[1]}</h3>
                <p class="job-company">🏢 {job[2]}</p>
                <p class="job-meta">
                    <span class="meta-item">📍 {job[3]}</span>
                    <span class="meta-item">💰 {salary_display}</span>
                </p>
                <p class="job-description">{description_snippet}</p>
                <a href="{job[5]}" class="apply-btn">View Full Job →</a>
            </div>
            """

        html_content = f"""
        <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); margin: 0; padding: 20px; }}
                    .container {{ background: white; border-radius: 12px; max-width: 750px; margin: 0 auto; box-shadow: 0 8px 16px rgba(0,0,0,0.1); padding: 30px; }}
                    .header {{ text-align: center; margin-bottom: 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; border-radius: 10px; }}
                    .emoji {{ font-size: 48px; margin-bottom: 10px; }}
                    h1 {{ color: white; margin: 0; font-size: 28px; font-weight: 600; }}
                    .count {{ color: #e0e0ff; font-size: 16px; margin-top: 5px; }}
                    .job-card {{ background: #f8f9ff; border-left: 4px solid #667eea; padding: 22px; margin: 18px 0; border-radius: 8px; }}
                    .job-card:hover {{ background: #f0f4ff; }}
                    .job-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
                    .job-number {{ display: inline-block; background: #667eea; color: white; width: 28px; height: 28px; border-radius: 50%; text-align: center; line-height: 28px; font-size: 12px; font-weight: bold; }}
                    .job-source {{ background: #e8d4f1; color: #764ba2; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
                    .job-title {{ color: #1a1a1a; margin: 10px 0 8px 0; font-size: 18px; font-weight: 600; line-height: 1.3; }}
                    .job-company {{ color: #555; margin: 6px 0 12px 0; font-size: 15px; font-weight: 500; }}
                    .job-meta {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0; font-size: 13px; }}
                    .meta-item {{ color: #666; }}
                    .job-description {{ color: #777; font-size: 13px; line-height: 1.5; margin: 12px 0; padding: 10px; background: #fff; border-radius: 4px; border-left: 2px solid #667eea; padding-left: 12px; }}
                    .apply-btn {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 10px 18px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 13px; margin-top: 8px; }}
                    .apply-btn:hover {{ opacity: 0.9; }}
                    .next-scan {{ background: #f0f4ff; padding: 15px; border-radius: 8px; color: #667eea; font-size: 13px; margin-top: 30px; text-align: center; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="emoji">🎯</div>
                        <h1>New Opportunities!</h1>
                        <div class="count">{len(jobs)} role{'s' if len(jobs) > 1 else ''} found</div>
                    </div>
                    <div class="jobs-list">
                        {job_rows}
                    </div>
                    <div class="next-scan">
                        ⏰ Next scan: {next_scan_time.strftime('%Y-%m-%d %H:%M IST')}
                    </div>
                </div>
            </body>
        </html>
        """

    msg.attach(MIMEText(html_content, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        print(f"✅ Email sent to {recipient}")
        return True
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False

def main():
    """Main scraper function"""
    current_time = get_ist_now()
    print(f"\n{'='*60}")
    print(f"🔍 Job Scraper Started - {current_time.strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"{'='*60}\n")

    init_db()

    # Determine search window
    is_first = is_first_run()
    search_hours = 24 if is_first else 1
    print(f"📊 First run: {is_first} - Searching last {search_hours} hour{'s' if search_hours > 1 else ''}\n")

    # Scrape all sources
    all_jobs = []
    print("📡 Scraping multiple sources...\n")

    all_jobs.extend(scrape_linkedin_jobs()) # LinkedIn/Indeed (free API)
    all_jobs.extend(scrape_arbeitnow())     # EU jobs (free API)
    all_jobs.extend(scrape_eures())         # EU Commission database
    all_jobs.extend(scrape_apify_vc_jobs()) # VC portfolio jobs

    print(f"\n📈 Total jobs found: {len(all_jobs)}")

    # Deduplicate
    dedup_jobs = deduplicate_jobs(all_jobs)
    print(f"🔄 After deduplication: {len(dedup_jobs)} unique jobs\n")

    # Filter jobs
    filtered_jobs = filter_jobs(dedup_jobs)
    print(f"✅ Matching 'Founder Associate' roles: {len(filtered_jobs)}\n")

    # Add new jobs to database
    new_count = 0
    for job in filtered_jobs:
        if add_job(job['job_hash'], job['title'], job['company'],
                   job['location'], job['salary'], job['url'],
                   job['description'], job['source']):
            new_count += 1

    print(f"💾 New jobs added to database: {new_count}\n")

    # Get recent jobs for email
    recent_jobs = get_recent_jobs(hours=search_hours)

    # Send email
    recipient = os.getenv('EMAIL_RECIPIENT', 'md.hamza.work@gmail.com')
    if recent_jobs:
        print(f"📧 Sending email with {len(recent_jobs)} jobs to {recipient}...")
        send_email(recipient, recent_jobs, no_jobs=False, search_hours=search_hours)
        mark_notified([job[0] for job in recent_jobs])
    else:
        print(f"📧 No new jobs found. Sending notification to {recipient}...")
        send_email(recipient, [], no_jobs=True, search_hours=search_hours)

    print(f"\n{'='*60}")
    print(f"✅ Scraper completed - {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
