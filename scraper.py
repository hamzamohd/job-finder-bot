import requests
import sqlite3
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import os
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# Database setup
DB_FILE = "jobs_database.db"

def init_db():
    """Initialize SQLite database to track seen jobs"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            job_id TEXT UNIQUE,
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

def job_exists(job_id):
    """Check if job already exists in database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM jobs WHERE job_id = ?", (job_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_job(job_id, title, company, location, salary, url, description, source):
    """Add new job to database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO jobs (job_id, title, company, location, salary, url, description, source, found_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (job_id, title, company, location, salary, url, description, source, datetime.now()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_recent_jobs(hours=1):
    """Get jobs found in the last N hours"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    time_threshold = datetime.now() - timedelta(hours=hours)
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

def scrape_indeed(location_code, last_24h=False):
    """Scrape Indeed for Founder Associate roles"""
    jobs = []
    location_map = {
        'UK': 'United Kingdom',
        'Berlin': 'Berlin, Germany',
        'Paris': 'Paris, France',
        'Amsterdam': 'Amsterdam, Netherlands'
    }

    for loc_key, loc_val in location_map.items():
        url = f"https://uk.indeed.com/jobs?q=Founder+Associate&l={loc_val}"
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                job_cards = soup.find_all('div', class_='job_seen_beacon')

                for card in job_cards[:5]:  # Limit to avoid rate limiting
                    title_elem = card.find('h2', class_='jobTitle')
                    company_elem = card.find('span', class_='companyName')
                    salary_elem = card.find('span', class_='salary-snippet')
                    location_elem = card.find('div', class_='companyLocation')
                    link_elem = card.find('a')

                    if title_elem and company_elem:
                        title = title_elem.get_text(strip=True)
                        if 'founder' in title.lower() and 'associate' in title.lower():
                            job_id = f"indeed_{link_elem.get('href', '').split('jk=')[-1] if link_elem else ''}"
                            jobs.append({
                                'job_id': job_id,
                                'title': title,
                                'company': company_elem.get_text(strip=True),
                                'location': location_elem.get_text(strip=True) if location_elem else loc_key,
                                'salary': salary_elem.get_text(strip=True) if salary_elem else 'Not specified',
                                'url': f"https://uk.indeed.com{link_elem.get('href', '')}" if link_elem else '',
                                'description': card.get_text(strip=True)[:200],
                                'source': 'Indeed'
                            })
        except Exception as e:
            print(f"Error scraping Indeed for {loc_key}: {e}")

    return jobs

def scrape_angellist():
    """Scrape AngelList for Founder Associate roles"""
    jobs = []
    locations = ['United Kingdom', 'Berlin', 'Paris']

    for location in locations:
        url = f"https://angel.co/job-board/search?roles=founder-associate&locations={location}"
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                # AngelList structure may vary, parsing job listings
                job_listings = soup.find_all('div', class_='job-item')
                for job in job_listings[:5]:
                    try:
                        title = job.find('a', class_='job-title')
                        company = job.find('span', class_='company-name')
                        if title and company:
                            job_id = f"angellist_{title.get_text(strip=True)}_{company.get_text(strip=True)}"
                            if job_id not in [j['job_id'] for j in jobs]:
                                jobs.append({
                                    'job_id': job_id,
                                    'title': title.get_text(strip=True),
                                    'company': company.get_text(strip=True),
                                    'location': location,
                                    'salary': 'Check on AngelList',
                                    'url': title.get('href', ''),
                                    'description': job.get_text(strip=True)[:200],
                                    'source': 'AngelList'
                                })
                    except:
                        pass
        except Exception as e:
            print(f"Error scraping AngelList for {location}: {e}")

    return jobs

def scrape_welcome_to_jungle():
    """Scrape Welcome to the Jungle for Founder Associate roles"""
    jobs = []
    locations = ['uk', 'berlin', 'paris']

    for loc in locations:
        url = f"https://www.welcometothejungle.com/en/jobs?keywords=founder%20associate&locations={loc}"
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                job_cards = soup.find_all('a', class_='job-card')

                for card in job_cards[:5]:
                    try:
                        job_id = f"wtj_{card.get('href', '').split('/')[-1]}"
                        title = card.find('span', class_='job-title')
                        company = card.find('span', class_='company')
                        if title and company:
                            jobs.append({
                                'job_id': job_id,
                                'title': title.get_text(strip=True),
                                'company': company.get_text(strip=True),
                                'location': loc.capitalize(),
                                'salary': 'Check on Welcome to the Jungle',
                                'url': f"https://www.welcometothejungle.com{card.get('href', '')}",
                                'description': card.get_text(strip=True)[:200],
                                'source': 'Welcome to the Jungle'
                            })
                    except:
                        pass
        except Exception as e:
            print(f"Error scraping Welcome to the Jungle for {loc}: {e}")

    return jobs

def scrape_google_jobs():
    """Search Google Job Board for Founder Associate roles"""
    jobs = []
    locations = ['London', 'Berlin', 'Paris']

    for location in locations:
        url = f"https://www.google.com/search?q=founder+associate+jobs+in+{location}"
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                # Google jobs integration (limited parsing)
                job_results = soup.find_all('div', class_='job-result')
                for result in job_results[:3]:
                    try:
                        title = result.find('h3')
                        company = result.find('div', class_='company')
                        if title:
                            job_id = f"google_{title.get_text(strip=True)}_{location}"
                            jobs.append({
                                'job_id': job_id,
                                'title': title.get_text(strip=True),
                                'company': company.get_text(strip=True) if company else 'Unknown',
                                'location': location,
                                'salary': 'Not specified',
                                'url': result.find('a').get('href', '') if result.find('a') else '',
                                'description': result.get_text(strip=True)[:200],
                                'source': 'Google Jobs'
                            })
                    except:
                        pass
        except Exception as e:
            print(f"Error scraping Google Jobs for {location}: {e}")

    return jobs

def filter_jobs(jobs):
    """Filter jobs based on criteria"""
    filtered = []
    keywords = ['founder', 'associate', 'founder associate']
    locations = ['uk', 'london', 'berlin', 'paris', 'amsterdam', 'netherlands', 'germany', 'france']
    min_salary = 30000

    for job in jobs:
        title_lower = job['title'].lower()
        location_lower = job['location'].lower()

        # Check title match
        has_founder = 'founder' in title_lower
        has_associate = 'associate' in title_lower
        if not (has_founder and has_associate):
            continue

        # Check location match
        location_match = any(loc in location_lower for loc in locations)
        if not location_match:
            continue

        # Check if job already in database
        if job_exists(job['job_id']):
            continue

        filtered.append(job)

    return filtered

def send_email(recipient, jobs, no_jobs=False):
    """Send HTML email with job listings"""
    sender = os.getenv('EMAIL_SENDER', 'job-finder-bot@gmail.com')
    password = os.getenv('EMAIL_PASSWORD', '')

    if not password:
        print("WARNING: EMAIL_PASSWORD not set. Email will not be sent.")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Job Finder Bot - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
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
                    <p>No new <strong>Founder Associate</strong> roles found in UK, Berlin, or Paris in the last hour.</p>
                    <div class="next-scan">
                        ⏰ Next scan: {(datetime.now() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M')} IST
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
            job_rows += f"""
            <div class="job-card">
                <div class="job-number">#{idx}</div>
                <h3 class="job-title">{job[1]}</h3>
                <p class="job-company">🏢 {job[2]}</p>
                <p class="job-meta">
                    <span class="meta-item">📍 {job[3]}</span>
                    <span class="meta-item">💰 {salary_display}</span>
                    <span class="meta-item">🔗 {job[7]}</span>
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
                    .job-card {{ background: #f8f9ff; border-left: 4px solid #667eea; padding: 22px; margin: 18px 0; border-radius: 8px; transition: transform 0.2s, box-shadow 0.2s; box-shadow: 0 2px 4px rgba(102, 126, 234, 0.1); }}
                    .job-card:hover {{ transform: translateX(5px); background: #f0f4ff; box-shadow: 0 4px 8px rgba(102, 126, 234, 0.2); }}
                    .job-number {{ display: inline-block; background: #667eea; color: white; width: 28px; height: 28px; border-radius: 50%; text-align: center; line-height: 28px; font-size: 12px; font-weight: bold; margin-bottom: 12px; }}
                    .job-title {{ color: #1a1a1a; margin: 10px 0 8px 0; font-size: 18px; font-weight: 600; line-height: 1.3; }}
                    .job-company {{ color: #555; margin: 6px 0 12px 0; font-size: 15px; font-weight: 500; }}
                    .job-meta {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0; font-size: 13px; }}
                    .meta-item {{ color: #666; }}
                    .job-description {{ color: #777; font-size: 13px; line-height: 1.5; margin: 12px 0; padding: 10px; background: #fff; border-radius: 4px; border-left: 2px solid #667eea; padding-left: 12px; }}
                    .apply-btn {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 10px 18px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 13px; margin-top: 8px; }}
                    .apply-btn:hover {{ opacity: 0.9; transform: scale(1.02); }}
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
                        ⏰ Next scan: {(datetime.now() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M')} IST
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
        print(f"Email sent to {recipient}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def main():
    """Main scraper function"""
    print(f"Starting job scraper at {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")

    init_db()

    # Scrape all sources
    all_jobs = []
    all_jobs.extend(scrape_indeed('UK', last_24h=False))
    all_jobs.extend(scrape_angellist())
    all_jobs.extend(scrape_welcome_to_jungle())
    all_jobs.extend(scrape_google_jobs())

    print(f"Found {len(all_jobs)} total jobs")

    # Filter jobs
    filtered_jobs = filter_jobs(all_jobs)
    print(f"Filtered to {len(filtered_jobs)} matching jobs")

    # Add new jobs to database
    new_job_ids = []
    for job in filtered_jobs:
        if add_job(job['job_id'], job['title'], job['company'],
                   job['location'], job['salary'], job['url'],
                   job['description'], job['source']):
            new_job_ids.append(job['job_id'])

    # Get recent jobs for email
    recent_jobs = get_recent_jobs(hours=1)

    # Send email
    recipient = os.getenv('EMAIL_RECIPIENT', 'md.hamza.work@gmail.com')
    if recent_jobs:
        print(f"Sending email with {len(recent_jobs)} new jobs")
        send_email(recipient, recent_jobs, no_jobs=False)
        mark_notified([job[0] for job in recent_jobs])
    else:
        print("No new jobs found, sending notification email")
        send_email(recipient, [], no_jobs=True)

    print(f"Scraper completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")

if __name__ == "__main__":
    main()
