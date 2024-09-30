from time import strftime
import requests
import urllib.parse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException
from datetime import datetime
import os
import sys
import json
import multiprocessing

##### HELPER FUNCTIONS #####

def check_for_element(driver, xpath, name):
	element = None
	try:
		element = driver.find_element(By.XPATH, xpath)
		if element and is_clickable(element):
			scroll_and_screenshot(driver, element, name)
			return True
	except NoSuchElementException:
		return False

def find_links(driver):
	links = set()
	current_domain = urllib.parse.urlparse(driver.current_url).netloc

	for link in driver.find_elements(By.TAG_NAME, "a"):
		href = link.get_attribute("href")
		parsed_url = urllib.parse.urlparse(link.get_attribute('href'))
		if href and parsed_url.netloc == current_domain and parsed_url.scheme in ["http", "https"]:
			links.add(href)
	return links

def is_clickable(element):
	try:
		return element.is_displayed() and element.is_enabled()
	except ElementNotInteractableException:
		return False

def scroll_and_screenshot(driver, element, name):
	driver.execute_script("arguments[0].scrollIntoView(true);", element)

	if not os.path.exists("screenshots"):
		os.makedirs("screenshots")
	driver.save_screenshot(f"screenshots/{name}.png")
	print(f"Screenshot saved for {name}.")

def file_saver(save_queue):
	now = datetime.now()
	filename = now.strftime("results_%Y-%m-%d_%H-%M.json")

	while True:
		updated_array = save_queue.get()

		if updated_array is None:
			break

		with open(filename, 'w') as f:
			json.dump(updated_array, f, indent=4)

############################


def crawl_site(args):
	shared_array, save_queue, url, name = args
	worker_id = multiprocessing.current_process()._identity[0] - 3

	print(f"Checking {name} ({url})")
	driver = webdriver.Firefox()

	print(worker_id)
	screen_width, screen_height = 1440, 875
	grid_cols, grid_rows = 3, 2
	window_width = screen_width // grid_cols
	window_height = screen_height // grid_rows

	# Calculate the position based on worker_id
	row = worker_id // grid_cols
	col = worker_id % grid_cols

	driver.set_window_size(window_width, window_height)
	driver.set_window_position(col * (window_width + 2), row * (window_height + 6))

	visited = set()
	result = {"name": name, "url": url, "status": ""}

	try:
		found = recursive_crawl(driver, url, name, visited)
		result["status"] = "Valid" if found else "Invalid"
	except Exception as e:
		print(e)
		result["status"] = str(e)
	finally:
		driver.quit()
		print(result)
		shared_array.append(result)
		save_queue.put(list(shared_array))

def recursive_crawl(driver, current_url, name, visited):
	# Base case: page already visited
	if current_url in visited:
		return False

	visited.add(current_url)
	driver.get(current_url)
	# Success case: webring links found
	if check_page(driver, current_url, name):
		return True

	# Failure case: begin searching for the links in subpages
	links = find_links(driver)

	priority_words = ["webring", "ring", "link"]
	ignored_words = ["blog", "updates", "talk", "thought", "note", "comic"]

	priority_links = [link for link in links if any(word in link for word in priority_words)]
	normal_links = [
		link for link in links
		if all(word not in link for word in priority_words) and all(ignored_word not in link for ignored_word in ignored_words)
]

	links = priority_links + normal_links
	print("links found:", links)

	for i in range(len(links)):
		if recursive_crawl(driver, links[i], name, visited):
			return True

	return False

def check_page(driver, url, name):
	name = urllib.parse.quote(name)

	redirect_urls = [f"https://webring.bucketfish.me/redirect.html?to=prev&name={name}",
				f"https://webring.bucketfish.me/redirect.html?to=next&name={name}",]
	embed_urls = [f"https://webring.bucketfish.me/embed.html?name={name}&lightmode=true",
				f"https://webring.bucketfish.me/embed.html?name={name}&lightmode=false",
				f"https://webring.bucketfish.me/embed.html?name={name}"]

	found_redirects = all([check_for_element(driver, f"//a[@href='{i}']", name) for i in redirect_urls])
	found_embed = any([check_for_element(driver, f"//iframe[@src='{i}']", name) for i in embed_urls])

	return (found_redirects or found_embed)


def main():
	response = requests.get("https://raw.githubusercontent.com/bucketfishy/bucket-webring/master/webring.json")
	urls = response.json()

	with multiprocessing.Manager() as manager:
			shared_array = manager.list()
			save_queue = manager.Queue()

			saver_process = multiprocessing.Process(target=file_saver, args=(save_queue,))
			saver_process.start()

			input_data_list = [(shared_array, save_queue, i["url"], i["name"]) for i in urls]

			with multiprocessing.Pool(processes=6) as pool:
				pool.map(crawl_site, input_data_list)

			# After all workers are done, send a sentinel to stop the file-saver process
			save_queue.put(None)

			saver_process.join()

if __name__ == "__main__":
    sys.setrecursionlimit(5)
    main()
