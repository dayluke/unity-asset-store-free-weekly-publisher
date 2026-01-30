import os
import re
import sys
import json
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, time, timezone
from emailoctopus_sdk import Client
from zoneinfo import ZoneInfo


# EmailOctopus Configuration - Get from GitHub Secrets
API_KEY = os.getenv("API_KEY")
LIST_ID = os.getenv("LIST_ID")

# Unity Asset Store Configuration and Selectors
ASSET_STORE_URL = "https://assetstore.unity.com"
ASSET_PARENT_SELECTOR = "[data-type='CalloutSlim']"
ASSET_NAME_SELECTOR = "h2"
ASSET_IMAGE_SELECTOR = "img"
ASSET_BUTTON_SELECTOR = "a"
ASSET_DESCRIPTION_SELECTOR = "body"
ASSET_PRICE_SELECTOR = "._3Yjml"

# Savings File Configuration
SAVINGS_FILE = "savings.json"


logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


# region: Unity Asset Store


def scrape_asset_info() -> tuple[str, str, str, str]:
	"""Scrapes the Unity Asset Store for the free asset of the week using new selectors."""
	try:
		url = f"{ASSET_STORE_URL}/publisher-sale"
		response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
		response.raise_for_status()
		soup = BeautifulSoup(response.content, "html.parser")

		free_asset_section = soup.select_one(ASSET_PARENT_SELECTOR)

		if free_asset_section:
			asset_name_element = free_asset_section.find(ASSET_NAME_SELECTOR)
			asset_name = asset_name_element.get_text(strip=True) if asset_name_element else "Asset Name Not Found"

			asset_image_element = free_asset_section.find(ASSET_IMAGE_SELECTOR)
			asset_image = asset_image_element.get("src") if asset_image_element else ""

			asset_button_element = free_asset_section.find(ASSET_BUTTON_SELECTOR)
			asset_url = asset_button_element.get("href") if asset_button_element else ""

			asset_description_element = free_asset_section.find(class_=ASSET_DESCRIPTION_SELECTOR)
			asset_description = asset_description_element.get_text(strip=True) if asset_description_element else "Asset Description Not Found"
			
			return asset_name, asset_image, asset_description, asset_url
		else:
			log.warning("Could not find the free asset section using the specified selector.")
			return None, None, None, None
			
	except requests.exceptions.RequestException as e:
		log.error(f"Error fetching the URL: {e}")
		return None, None, None, None


def next_weekday_at_time(weekday: int, target_time: time, tz=timezone.utc) -> datetime:
	now = datetime.now(tz)
	days_ahead = (weekday - now.weekday() + 7) % 7
	if days_ahead == 0 and now.time() >= target_time:
		days_ahead = 7

	next_day = (now + timedelta(days=days_ahead)).date()
	return datetime.combine(next_day, target_time, tzinfo=tz)


def get_expiry_date() -> str:
	# Get next Thursday at 8:00 AM PT
	pt_tz = ZoneInfo("America/Los_Angeles")
	next_thursday_8am_pt = next_weekday_at_time(weekday=3, target_time=time(8, 0), tz=pt_tz)
	# Convert to UTC
	next_thursday_utc = next_thursday_8am_pt.astimezone(timezone.utc)
	# Format it like: October 2, 2025 at 3:00PM UTC
	return next_thursday_utc.strftime("%B %-d, %Y at %-I:%M%p UTC")


# endregion: Unity Asset Store

# region: Email Octopus


def update_all_contacts_fields(asset: str, image: str, description: str, url: str) -> int:
	"""Updates all subscribers' asset-related fields, triggering the automation to send the email."""
	client = Client(api_key=API_KEY)
	contacts = client.get_all_contacts(list_id=LIST_ID)
	expiry_date = get_expiry_date()
	fields = {
		"AssetName": asset,
		"AssetImage": image,
		"AssetDescription": description,
		"AssetURL": url,
		"AssetExpiry": expiry_date
	}

	success_count = 0
	failed_count = 0
	for batch in client.update_contacts_in_batches(list_id=LIST_ID, contacts=contacts, fields=fields):
		success_count += len(batch['success'])
		failed_count += len(batch['errors'])

	for field in fields:
		# Format the label with spaces between words
		label = re.sub(r'([a-z])([A-Z])', r'\1 \2', field)
		log.info(f"Updating {label}'s fallback value to: {fields[field]}")
		client.update_list_field(list_id=LIST_ID, tag=field, label=label, fallback=fields[field])
	
	log.info(f"Success: {success_count}, Failed: {failed_count}")

	return success_count


# endregion: Email Octopus

# region: Price Scraping


def scrape_asset_price(asset_url: str) -> float:
	"""Visits the asset's page and scrapes its regular price."""
	if not asset_url.startswith("https://"):
		asset_url = ASSET_STORE_URL + asset_url

	try:
		log.info(f"Scraping price from: {asset_url}")
		headers = { 'User-Agent': 'Mozilla/5.0' }
		cookies = { 'AC_CURR': 'USD' }
		response = requests.get(asset_url, headers=headers, cookies=cookies)
		response.raise_for_status()
		soup = BeautifulSoup(response.content, "html.parser")
		
		price_element = soup.select_one(ASSET_PRICE_SELECTOR)

		if price_element:
			price_text = price_element.contents[-1].get_text(strip=True)
			log.info(f"Found price: {price_text}")
			number = float(price_text.replace("$", ""))
			return number
		else:
			log.warning("Could not find the price element on the page.")
			return 0.0
	except requests.exceptions.RequestException as e:
		log.error(f"Error fetching the asset price URL: {e}")
		return 0.0


def read_total_savings() -> tuple[float, int, float, int]:
	"""Reads the total savings, number of assets, and cumulative savings from the JSON file."""
	try:
		with open(SAVINGS_FILE, 'r') as f:
			data = json.load(f)
			current_savings = float(data.get("total_savings", 0.0))
			current_assets = int(data.get("total_assets", 0))
			current_cumulative_savings = float(data.get("total_cumulative_savings", 0.0))
			current_emails_sent = int(data.get("total_emails_sent", 0))
			return current_savings, current_assets, current_cumulative_savings, current_emails_sent
	except FileNotFoundError:
		log.warning(f"'{SAVINGS_FILE}' not found. Starting savings from 0.")
		return 0.0, 0, 0.0, 0
	except (json.JSONDecodeError, TypeError):
		log.error(f"Could not read or parse '{SAVINGS_FILE}'. Treating savings as 0.")
		return 0.0, 0, 0.0, 0


def save_total_savings(new_total: float, new_assets: int, new_cumulative_savings: float, new_emails_sent: int) -> None:
	"""Saves the new total savings, number of assets, cumulative savings, and number of emails sent to the JSON file."""
	data = {
		"total_savings": round(new_total, 2),
		"total_assets": new_assets,
		"total_cumulative_savings": round(new_cumulative_savings, 2),
		"total_emails_sent": new_emails_sent,
		"last_run_date": datetime.now(tz=ZoneInfo("America/Los_Angeles")).date().isoformat(),
	}
	with open(SAVINGS_FILE, 'w') as f:
		json.dump(data, f, indent=2)
	log.info(f"Successfully saved new total savings: {data['total_savings']:.2f}, number of assets: {data['total_assets']}, cumulative savings: {data['total_cumulative_savings']:.2f}, emails sent: {data['total_emails_sent']}, last run date: {data['last_run_date']}")


# endregion: Price Scraping

# region: Main


def should_run_now(now_pt: datetime) -> bool:
	"""
	Determines if the script should proceed based on time and previous runs.
	Returns True if we should send the email, False otherwise.
	"""
	# 1. Setup current time in iso format
	today_str = now_pt.date().isoformat()
	
	log.info(f"Current Time (PT): {now_pt.strftime('%Y-%m-%d %H:%M:%S')}")

	# 2. Check that it is Thursday
	if now_pt.weekday() != 3: 
		log.info("Today is not Thursday. Exiting.")
		return False

	# 3. Check that it is after 8:30 AM PT
	# We use >= 8:30 to prevent the Winter 7:30 AM run from triggering,
	# but allow delayed jobs (e.g. 9:00 AM) to still work.
	if now_pt.time() < time(8, 30):
		log.info("It is too early (before 8:30 AM PT). Exiting.")
		return False

	# 4. Check that we have not already run today
	try:
		with open(SAVINGS_FILE, 'r') as f:
			data = json.load(f)
			last_run = data.get("last_run_date")
	except (FileNotFoundError, json.JSONDecodeError):
		log.warning(f"Could not read '{SAVINGS_FILE}'. Returning empty data.")
		last_run = None
	
	if last_run and last_run == today_str:
		log.info(f"Script already ran successfully today ({today_str}). Exiting.")
		return False

	return True


def main():
	# Check if the script was run manually or by the schedule
	RUN_CONTEXT = os.getenv("RUN_CONTEXT")

	if RUN_CONTEXT == "schedule":
		target_tz = ZoneInfo("America/Los_Angeles")
		current_pt_time = datetime.now(target_tz)
		if not should_run_now(current_pt_time):
			log.info(f"Not the right time or already ran today. Current PT: {current_pt_time.strftime('%A %H:%M')}. Exiting.")
			sys.exit(0) # Exit with success, but do nothing
			
		log.info(f"Correct time ({current_pt_time.strftime('%H:%M PT')}) detected. Running script...")
	elif RUN_CONTEXT == "workflow_dispatch":
		log.info("Run triggered by 'workflow_dispatch'. Bypassing time check.")
	else:
		log.info(f"Run context is '{RUN_CONTEXT}'. Bypassing time check.")
	
	log.info("Starting the Unity Asset Notifier script...")
	
	missing_vars = []
	if not API_KEY:
		missing_vars.append("API_KEY")
	if not LIST_ID:
		missing_vars.append("LIST_ID")
	
	if missing_vars:
		log.error(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
		sys.exit(2)
	
	asset, image, description, url = scrape_asset_info()
	if not all ([asset, description, image, url]):
		log.warning("Could not find asset information. No fields will be updated.")
		sys.exit(3)
	
	log.info(f"Found asset: {asset}")
	
	try:
		successful_subscribers = update_all_contacts_fields(asset, image, description, url)

		asset_price = scrape_asset_price(url)
		if asset_price > 0.0:
			current_savings, current_assets, current_cumulative_savings, current_emails_sent = read_total_savings()
			new_savings = current_savings + asset_price
			new_assets = current_assets + 1
			new_cumulative_savings = current_cumulative_savings + (asset_price * successful_subscribers)
			new_emails_sent = current_emails_sent + successful_subscribers
			save_total_savings(new_savings, new_assets, new_cumulative_savings, new_emails_sent)
		else:
			log.warning("Asset price is 0 or could not be found. Savings will not be updated.")
		
		sys.exit(0)
	except Exception as e:
		log.error(f"Unexpected error while updating fields: {e}")
		sys.exit(1)


if __name__ == "__main__":
	main()


# endregion: Main

# Exit code defintions:
# 0 = success
# 1 = generic error
# 2 = missing config
# 3 = data issue (e.g. asset not found)
