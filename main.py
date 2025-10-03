import os
import sys
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, time, timezone


# Brevo Configuration - Get from GitHub Secrets
API_KEY = os.getenv("API_KEY")
LIST_ID = os.getenv("LIST_ID")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
TEMPLATE_ID = os.getenv("TEMPLATE_ID")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

def scrape_asset_info():
    """Scrapes the Unity Asset Store for the free asset of the week using new selectors."""
    try:
        url = "https://assetstore.unity.com/publisher-sale"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        selector = "[data-type='CalloutSlim']"
        free_asset_section = soup.select_one(selector)

        if free_asset_section:
            asset_name_element = free_asset_section.find("h2")
            asset_name = asset_name_element.get_text(strip=True) if asset_name_element else "Asset Name Not Found"

            asset_image_element = free_asset_section.find("img")
            asset_image = asset_image_element.get("src") if asset_image_element else ""

            asset_button_element = free_asset_section.find("a")
            asset_url = asset_button_element.get("href") if asset_button_element else ""

            asset_description_element = free_asset_section.find(class_="body")
            asset_description = asset_description_element.get_text(strip=True) if asset_description_element else "Asset Description Not Found"
            
            return asset_name, asset_image, asset_description, asset_url
        else:
            log.warning("Could not find the free asset section using the specified selector.")
            return None, None, None, None
            
    except requests.exceptions.RequestException as e:
        log.error(f"Error fetching the URL: {e}")
        return None, None, None, None


def next_weekday_at_time(weekday: int, target_time: time, tz=timezone.utc):
    now = datetime.now(tz)
    days_ahead = (weekday - now.weekday() + 7) % 7
    if days_ahead == 0 and now.time() >= target_time:
        days_ahead = 7

    next_day = (now + timedelta(days=days_ahead)).date()
    return datetime.combine(next_day, target_time, tzinfo=tz)


def get_expiry_date():
    # Get next Thursday at 15:00 UTC
    next_thursday_3pm_utc = next_weekday_at_time(weekday=3, target_time=time(15, 0))
    # Format it like: October 2, 2025 at 3:00PM UTC
    return next_thursday_3pm_utc.strftime("%B %-d, %Y at %-I:%M%p UTC")


def get_contacts_from_list():
    """Fetches all contacts from a specific Brevo list."""
    url = f"https://api.brevo.com/v3/contacts/lists/{LIST_ID}/contacts"
    headers = {
        "accept": "application/json",
        "api-key": API_KEY
    }

    log.info(f"Fetching contacts from list ID {LIST_ID}...")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        contacts = [
            { "email": contact["email"] }
            for contact in response.json().get("contacts", [])
        ]

        log.info(f"Found {len(contacts)} contacts.")
        return contacts

    except requests.RequestException as e:
        log.error(f"Error fetching contacts: {e}")
        return None


def send_template_to_contacts(contacts_to_send, params):
    """Sends a transactional template to a list of contacts."""
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": API_KEY,
        "content-type": "application/json"
    }

    payload = {
        "sender": {"email": SENDER_EMAIL, "name": "Unity Asset Notifier"},
        "replyTo": {"email": SENDER_EMAIL, "name": "Luke Day"},
        "bcc": contacts_to_send,
        "templateId": int(TEMPLATE_ID),
        "params": params
    }

    log.info(f"Sending template {TEMPLATE_ID} to {len(contacts_to_send)} contacts...")

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        log.info("Email sent successfully via Brevo transactional API")
    except requests.exceptions.RequestException as e:
        log.error(f"An API error occurred while sending: {e}")
        if e.response:
            log.error("Error details:", e.response.text)

def main():
    log.info("Starting the Unity Asset Notifier script...")

    if not all([API_KEY, LIST_ID, SENDER_EMAIL, TEMPLATE_ID]):
        log.error("Error: Missing one or more required environment variables.")
        sys.exit(2)
    
    asset, image, description, url = scrape_asset_info()
    if not all ([asset, description, image, url]):
        log.warning("Could not find asset information. No email will be sent.")
        sys.exit(3)
    
    log.info(f"Found asset: {asset}")
    
    subscribers = get_contacts_from_list()
    if not subscribers:
        log.warning("No subscribers found. Aborting email send.")
        sys.exit(4)
    
    email_params = {
        "asset_name": asset,
        "asset_description": description,
        "asset_image": image,
        "asset_url": url,
        "expiry_date_formatted": get_expiry_date()
    }
    
    try:
        send_template_to_contacts(subscribers, email_params)
        sys.exit(0)
    except Exception as e:
        log.error(f"Unexpected error while sending email: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

# Exit code defintions:
# 0 = success
# 1 = generic error
# 2 = missing config
# 3 = data issue (e.g. asset not found)
# 4 = no contacts