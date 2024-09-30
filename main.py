import json
import time
import os
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException
import requests
import urllib.parse

driver = webdriver.Safari()

def is_clickable(element):
	try:
		return element.is_displayed() and element.is_enabled()
	except (NoSuchElementException, ElementNotInteractableException):
		return False

def scroll_and_screenshot(element, name):
	driver.execute_script("arguments[0].scrollIntoView(true);", element)
	time.sleep(1)

	if not os.path.exists("screenshots"):
		os.makedirs("screenshots")
	element.screenshot(f"screenshots/{name}.png")
	print(f"Screenshot saved for {name}.")

def check_for_element(xpath, name):
	print(xpath)
	element = None
	try:
		element = driver.find_element(By.XPATH, xpath)
		if element and is_clickable(element):
				scroll_and_screenshot(element, name)
				return True
	except NoSuchElementException:
		return False

def check_webring_links(driver, name):
	name = urllib.parse.quote(name)

	redirect_urls = [f"https://webring.bucketfish.me/redirect.html?to=prev&name={name}",
				f"https://webring.bucketfish.me/redirect.html?to=next&name={name}",]
	embed_urls = [f"https://webring.bucketfish.me/embed.html?name={name}&lightmode=true",
				f"https://webring.bucketfish.me/embed.html?name={name}&lightmode=false",
				f"https://webring.bucketfish.me/embed.html?name={name}"]

	found_redirects = all([check_for_element(f"//a[@href='{i}']", name) for i in redirect_urls])
	found_embed = any([check_for_element(f"//iframe[@src='{i}']", name) for i in embed_urls])

	return (found_redirects or found_embed)

def check_http_status(url):
	try:
		response = requests.head(url)
		return response.status_code
	except requests.exceptions.RequestException:
		return None

def crawl_site(driver, base_url):
	links = set()
	for link in driver.find_elements(By.TAG_NAME, "a"):
		href = link.get_attribute("href")
		if href and href.startswith(base_url):
			links.add(href)
	return links

def process_urls(json_url, output_file):
	response = requests.get(json_url)
	urls = response.json()

	if os.path.exists(output_file):
		with open(output_file, 'r') as file:
			try:
				results = json.load(file)
			except json.JSONDecodeError:
				results = []
	else:
		results = []

	for entry in urls:
		name = entry['name']
		url = entry['url']

		print(f"Checking {name}: {url}")

		# Check base URL status
		status = check_http_status(url)
		if status and status >= 400:
			result = {"name": name, "url": url, "status": f"Error: {status}"}
			results.append(result)
			save_results(results, output_file)  # Save after processing each site
			continue

		# Load the page in Selenium
		try:
			driver.get(url)
			driver.implicitly_wait(2)  # Allow some time for the page to load

			# Check for the webring links/iframes
			if check_webring_links(driver, name):
				result = {"name": name, "url": url, "status": "Valid"}
			else:
				# Crawl all links if not found directly
				links = crawl_site(driver, url)
				found = False
				for link in links:
					driver.get(link)
					driver.implicitly_wait(2)
					if check_webring_links(driver, name):
						result = {"name": name, "url": link, "status": "Valid"}
						found = True
						break
				if not found:
					result = {"name": name, "url": url, "status": "Invalid: Links not found"}

			results.append(result)
			save_results(results, output_file)  # Save after processing each site

		except Exception as e:
			print(e)
			result = {"name": name, "url": url, "status": f"Error: {str(e)}"}
			results.append(result)
			save_results(results, output_file)  # Save after processing each site


def save_results(results, output_file):
	with open(output_file, 'w') as file:
		json.dump(results, file, indent=4)

if __name__ == "__main__":
	json_file = "https://raw.githubusercontent.com/bucketfishy/bucket-webring/master/webring.json"  # Replace with your JSON file path
	output_file = "results.json"
	process_urls(json_file, output_file)
	driver.quit()
