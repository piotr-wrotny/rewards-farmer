import os
import random
import sys
import time
from typing import Callable
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException
import tab_utils
import llm_utils
import mouse_trajectory
import mimic_typing
import element_selectors

VISUAL_SEARCH_ASSET_CANDIDATES = (
	"/data/edge-profile/visual-search-asset.jpg",
	"/data/edge-profile/visual_search.jpg",
	"visual-search-asset.jpg",
	"visual_search.jpg",
)
VISUAL_SEARCH_RUNS = 30
FALLBACK_SEARCH_RUNS = 35
REQUIRED_SEARCH_RUNS = 30
SEARCH_PHRASE_POOL_SIZE = 600
SEARCH_SCROLL_STEP_RANGE = (120, 360)
SEARCH_SCROLL_STEPS_PER_QUERY = (1, 3)
SEARCH_DWELL_SECONDS = (5.0, 6.0)
SEARCH_QUERY_TEMPLATES = (
	"{noun} facts",
	"{noun} history",
	"{noun} benefits",
	"{noun} examples",
	"{noun} guide {year}",
	"best {noun} tips",
	"how to use {noun}",
	"{noun} for beginners",
	"{noun} near me",
	"{noun} latest news",
	"{noun} interesting trivia",
	"{noun} comparison",
)

class RewardsTaskUtils:
	def __init__(self, driver: webdriver.Edge):
		self.driver = driver

		self.driver.get("https://rewards.bing.com/")

		self.tab_utils = tab_utils.TabUtils(driver)
		self.tab_utils.ensure_focus()

		self.mouse = mouse_trajectory.MouseUtils(driver)
		self.keyboard = mimic_typing.KeyboardUtils(driver)
		self.elements = element_selectors.ElementSelectionUtils(driver)
		self.visual_search_image_path = self.resolve_visual_search_asset_path()

	def find_element(self, xpath: str):
		return self.driver.find_element(By.XPATH, xpath)

	def wait_for_element(self, element_getter: Callable[[], WebElement | list[WebElement]], timeout: int = 10) -> WebElement | list[WebElement]:
		def condition(_: webdriver.Edge):
			try:
				element_or_elements = element_getter()

				return element_or_elements
			except:
				return False

		return WebDriverWait(self.driver, timeout).until(condition)

	def switch_to_earn_page(self):
		self.move_to_and_click(self.elements.get_earn_tab())

	def switch_to_dashboard(self):
		self.move_to_and_click(self.elements.get_dashboard_tab())

	def move_to_and_click(self, elem: WebElement):
		self.mouse.move_to_element(elem)
		self.mouse.human_like_click()

	def wait_for_then_click(self, element_getter: Callable[[], WebElement], timeout: int = 10):
		elem = self.wait_for_element(element_getter, timeout)
		self.move_to_and_click(elem)

	def log_action(self, context: str, detail: str, trigger: str):
		print(f"[ACTION] {context} [{detail}] trigger={trigger}")

	def resolve_visual_search_asset_path(self) -> str:
		for candidate in VISUAL_SEARCH_ASSET_CANDIDATES:
			path = candidate if os.path.isabs(candidate) else os.path.abspath(candidate)
			if os.path.exists(path):
				print(f"[INFO] Visual search asset: {path}")
				return path

		raise FileNotFoundError(
			"No visual search asset found. Provide one of: "
			+ ", ".join(VISUAL_SEARCH_ASSET_CANDIDATES)
		)

	def resolve_positive_int_env(self, name: str, default: int) -> int:
		value = os.environ.get(name)
		if value is None:
			return default

		try:
			parsed = int(value)
		except ValueError:
			print(f"[WARNING] Ignoring invalid {name}={value!r}; expected integer")
			return default

		if parsed <= 0:
			print(f"[WARNING] Ignoring invalid {name}={value!r}; expected > 0")
			return default

		return parsed

	def complete_bing_daily_set(self, expected_activities: int = 3):
		self.switch_to_earn_page()

		self.wait_for_then_click(self.elements.get_open_daily_set_button)

		# The panel hydrates progressively, so the first non-empty snapshot can
		# hold fewer than 3 activities. wait_for_element returns on the first
		# truthy result, so a 1-element list satisfied it and indexing [1] and
		# [2] then raised IndexError, taking the whole task down. Wait for the
		# full set instead, and if it never fills, work with what is there.
		def full_activity_list():
			activities = self.elements.get_daily_set_elements()

			return activities if len(activities) >= expected_activities else False

		try:
			daily_set_links = self.wait_for_element(full_activity_list, timeout=30)
		except TimeoutException:
			daily_set_links = self.elements.get_daily_set_elements()

			print(f"[WARNING] Daily set panel only shows {len(daily_set_links)} of {expected_activities} activities")

		# Re-read the panel per index: clicking an activity can re-render it and
		# stale the captured references.
		for index in range(len(daily_set_links)):
			activities = self.elements.get_daily_set_elements()

			if index >= len(activities):
				break

			description = self.elements.extract_card_descriptions(activities[index])
			self.log_action("Daily set", description, "Rewards daily set activity")
			self.move_to_and_click(activities[index])
			time.sleep(random.uniform(2, 3))
			self.driver.switch_to.window(self.driver.current_window_handle) # refocus on the main tab

		self.tab_utils.close_all_other_tabs()

	def complete_explore_on_bing_tasks(self):
		self.switch_to_earn_page()

		explore_on_bing_links = self.elements.get_explore_on_bing_elements()

		if not explore_on_bing_links:
			# Raise rather than return, so complete_all_tasks reports this as
			# [SKIP]. Returning quietly made it print [OK] for a task that never
			# ran, which is exactly the kind of false success a scheduled run
			# must not produce.
			raise NoSuchElementException("no Explore on Bing section in this UI variant")

		for card in explore_on_bing_links:
			desc = self.elements.extract_card_descriptions(card)
			query = llm_utils.get_search_query_from_task_description(desc)
			self.log_action("Explore on Bing", query, desc)

			self.move_to_and_click(card)
			self.tab_utils.switch_to_other_tab()

			self.wait_for_element(self.elements.get_bing_search_bar)

			# search bar should be auto-focused

			self.keyboard.send_keys(f"{query} -noai{Keys.ENTER}")

			time.sleep(random.uniform(2, 3))

			self.tab_utils.switch_to_other_tab()
			self.tab_utils.close_all_other_tabs()

		time.sleep(random.uniform(1, 2)) # allow card statuses to update

		for card in explore_on_bing_links:
			if not self.elements.card_is_complete(card):
				print(f"[WARNING] Explore on Bing Card [desc={self.elements.extract_card_descriptions(card)!r}] is not complete after searching. Please check manually.")

	def complete_visual_search(self, runs: int = VISUAL_SEARCH_RUNS):
		runs = self.resolve_positive_int_env("VISUAL_SEARCH_RUNS", runs)
		print(f"[INFO] Running visual search count: {runs}")

		# Preferred path: open from Rewards sidebar. Some variants do not expose
		# it there, so fall back to Bing camera directly.
		try:
			self.switch_to_earn_page()
			self.wait_for_then_click(self.elements.get_open_visual_search_sidebar)
			self.wait_for_then_click(self.elements.get_search_now_link_from_visual_search_sidebar)
			self.tab_utils.switch_to_other_tab()
		except (NoSuchElementException, TimeoutException):
			self.driver.get("https://www.bing.com/")
			self.tab_utils.ensure_focus()

		completed = 0

		for run_index in range(runs):
			self.driver.get("https://www.bing.com/")
			self.tab_utils.ensure_focus()

			try:
				self.wait_for_then_click(self.elements.get_visual_search_button, timeout=20)
				file_input = self.wait_for_element(self.elements.get_visual_search_file_input, timeout=20)
				file_input.send_keys(self.visual_search_image_path)
				completed += 1
				self.log_action(
					"Visual search",
					f"{completed}/{runs}",
					f"asset={os.path.basename(self.visual_search_image_path)}"
				)
				time.sleep(random.uniform(3, 5))
			except (NoSuchElementException, TimeoutException, ValueError):
				print(f"[WARNING] Visual search controls missing on run {run_index + 1}/{runs}")
				time.sleep(random.uniform(1, 2))

		if completed == 0:
			raise NoSuchElementException("visual search controls not available on bing.com")

		self.tab_utils.close_all_other_tabs()

	def complete_misc_cards(self):
		self.switch_to_earn_page()

		misc_cards: list[WebElement] = self.wait_for_element(self.elements.get_all_misc_cards)

		for card in misc_cards:
			self.mouse.wheel_scroll_element_into_view(card)

			if not self.elements.card_is_complete(card) and self.elements.get_card_point_value(card) > 0:
				self.move_to_and_click(card)
				time.sleep(random.uniform(1, 2))
				self.driver.switch_to.window(self.driver.current_window_handle)

		for card in misc_cards:
			if not self.elements.card_is_complete(card) and self.elements.get_card_point_value(card) > 0:
				print(f"[WARNING] Misc Card [desc={self.elements.extract_card_descriptions(card)!r}] is not complete after clicking. Please check manually.")

		self.tab_utils.close_all_other_tabs()

		self.mouse.wheel_scroll_to_top()

	def complete_required_searches(self):
		# Run a fixed number of searches every time.
		# This keeps behavior stable even when the Rewards points breakdown
		# panel is unavailable or translated differently.
		runs = self.resolve_positive_int_env("REQUIRED_SEARCH_RUNS", REQUIRED_SEARCH_RUNS)
		print(f"[INFO] Running required searches: {runs}")

		try:
			self.run_search_batch(runs)
		except Exception as exc:
			print(
				f"[WARNING] Required search batch failed ({type(exc).__name__}); "
				f"retrying with fallback batch of {FALLBACK_SEARCH_RUNS}."
			)
			self.run_search_batch(FALLBACK_SEARCH_RUNS)

	def read_search_points(self):
		"""Open the points breakdown, read the Bing search row, close it again."""
		self.switch_to_earn_page()

		# 30s rather than the default 10s: this runs after the earlier tasks have
		# navigated away, so the earn page re-renders from scratch first and the
		# breakdown button regularly needs longer than 10s to appear. Timing out
		# here skipped the entire search task while points were still available.
		self.wait_for_then_click(self.elements.get_points_breakdown_button, timeout=30)

		close_btn = self.wait_for_element(self.elements.get_close_button_on_points_breakdown, timeout=15)

		points_earned, max_pts = self.elements.get_points_earned_from_searches_on_points_breakdown()

		try:
			self.move_to_and_click(close_btn)
		except Exception:
			pass

		return points_earned, max_pts

	def run_search_batch(self, count: int):
		self.driver.get("https://www.bing.com/")
		self.tab_utils.ensure_focus()

		self.wait_for_element(self.elements.get_bing_search_bar)

		# search bar should be auto-focused
		phrase_pool = self.build_search_phrase_pool()

		try:
			queries = random.sample(phrase_pool, count)
		except Exception as exc:
			queries = [random.choice(phrase_pool) for _ in range(count)]
			print(
				f"[WARNING] Could not sample unique search queries ({type(exc).__name__}); "
				"using sampled-with-replacement queries."
			)

		for i, query in enumerate(queries):
			self.log_action("Required searches", f"{i+1}/{count} {query}", "Fixed search batch")
			self.keyboard.send_keys(f"{query} -noai{Keys.ENTER}")
			self.random_scroll_and_dwell_after_search()

			try:
				self.wait_for_then_click(self.elements.get_clear_bing_search_query_button, timeout=3)
			except (StaleElementReferenceException, NoSuchElementException, TimeoutException, ValueError):
				# Some Bing variants do not expose the clear button consistently.
				# Keep progressing searches by clearing via keyboard instead.
				try:
					self.wait_for_then_click(self.elements.get_bing_search_bar, timeout=3)
				except (NoSuchElementException, TimeoutException):
					pass

				self.keyboard.send_keys(f"{Keys.CONTROL}a{Keys.DELETE}")

		self.driver.get("https://rewards.bing.com/")
		self.tab_utils.ensure_focus()

	def random_scroll_and_dwell_after_search(self):
		"""Scroll down by a random amount and wait after each search."""
		steps = random.randint(*SEARCH_SCROLL_STEPS_PER_QUERY)
		total_distance = 0

		for _ in range(steps):
			distance = random.randint(*SEARCH_SCROLL_STEP_RANGE)
			ActionChains(self.driver).scroll_by_amount(0, distance).perform()
			total_distance += distance
			time.sleep(random.uniform(0.08, 0.2))

		dwell = random.uniform(*SEARCH_DWELL_SECONDS)
		print(f"[INFO] Search page scroll={total_distance}px dwell={dwell:.2f}s")
		time.sleep(dwell)

	def build_search_phrase_pool(self) -> list[str]:
		"""Build a large phrase pool from nouns, sampled randomly every run."""
		nouns = list({noun.strip().lower() for noun in llm_utils.NOUNS if noun.strip()})

		if not nouns:
			return [f"general topic {i+1}" for i in range(SEARCH_PHRASE_POOL_SIZE)]

		random.shuffle(nouns)
		years = (2024, 2025, 2026)
		pool: list[str] = []

		for noun in nouns:
			template = random.choice(SEARCH_QUERY_TEMPLATES)
			pool.append(template.format(noun=noun, year=random.choice(years)))

			if len(pool) >= SEARCH_PHRASE_POOL_SIZE:
				break

		if len(pool) < SEARCH_PHRASE_POOL_SIZE:
			while len(pool) < SEARCH_PHRASE_POOL_SIZE:
				noun = random.choice(nouns)
				template = random.choice(SEARCH_QUERY_TEMPLATES)
				pool.append(template.format(noun=noun, year=random.choice(years)))

		print(f"[INFO] Built search phrase pool: {len(pool)}")
		return pool

	def claim_bonus_points(self):
		self.switch_to_dashboard()

		self.wait_for_then_click(self.elements.get_bonus_button_on_dashboard)

		try:
			self.wait_for_then_click(self.elements.get_claim_bonus_points_button)
		except TimeoutException:
			print("[WARNING] Could not find the 'Claim Bonus Points' button. There are likely no bonus points to claim at this time.")

	def verify_signed_in(self) -> int:
		"""Login probe for provisioning web profiles: the signed-in Rewards page
		renders the earn tab; a logged-out one redirects to the sign-in wall.
		Exit codes (like the mobile factory probe): 0 signed in, 2 wall/failure."""
		url = self.driver.current_url.lower()
		if "account.microsoft.com" in url or "login.live" in url or "signin" in url:
			print(f"[ACTION] login_check [redirected to sign-in: {url}] trigger=verify_signed_in")
			print("state=wall")
			return 2
		try:
			self.wait_for_element(self.elements.get_earn_tab, timeout=60)
		except TimeoutException:
			print(f"[ACTION] login_check [earn tab never rendered at {self.driver.current_url}] trigger=verify_signed_in")
			print("state=wall")
			return 2
		print("state=signed_in")
		return 0

	def complete_all_tasks(self):
		# Each task is run independently. The Rewards UI differs by market and
		# changes between deploys, so a task the current variant does not ship
		# must not take the remaining ones down with it.
		steps = (
			("Bing daily set", self.complete_bing_daily_set),
			("Explore on Bing", self.complete_explore_on_bing_tasks),
			("Visual search", self.complete_visual_search),
			("Misc cards", self.complete_misc_cards),
			("Required searches", self.complete_required_searches),
			("Bonus points", self.claim_bonus_points),
		)

		requested_task = os.environ.get("REWARDS_TASK", "all").strip().lower()

		# 'login_check' is a provisioning probe, not a Rewards activity: it never
		# joins the 'all' flow and reports its state through the exit code.
		if requested_task == "login_check":
			sys.exit(self.verify_signed_in())

		task_aliases = {
			"all": "all",
			"bing_daily_set": "Bing daily set",
			"explore": "Explore on Bing",
			"explore_on_bing": "Explore on Bing",
			"visual": "Visual search",
			"visual_search": "Visual search",
			"misc": "Misc cards",
			"misc_cards": "Misc cards",
			"searches": "Required searches",
			"required_searches": "Required searches",
			"bonus": "Bonus points",
			"bonus_points": "Bonus points",
		}

		if requested_task not in task_aliases:
			raise ValueError(
				f"Unknown REWARDS_TASK={requested_task!r}. "
				f"Supported values: {', '.join(sorted(task_aliases.keys()))}"
			)

		selected_task_name = task_aliases[requested_task]

		if selected_task_name != "all":
			steps = tuple(step for step in steps if step[0] == selected_task_name)
			print(f"[INFO] Running single task mode: {selected_task_name}")

		for name, step in steps:
			try:
				step()
				print(f"[OK] {name}")
			except (NoSuchElementException, TimeoutException) as exc:
				print(f"[SKIP] {name}: not available in this UI variant ({type(exc).__name__})")
			except Exception as exc:
				print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")

			# Leave a clean tab state behind for the next task.
			try:
				self.tab_utils.close_all_other_tabs()
			except Exception:
				pass