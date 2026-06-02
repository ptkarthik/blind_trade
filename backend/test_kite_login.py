"""Selenium-based Kite auto-login with screenshots for debugging."""
import time
import pyotp
import urllib.parse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.options import Options

API_KEY = "3dabnjscghrlof6y"
API_SECRET = "1jscg76sah89qpbmg1edn74sbj1n67e8"
USER_ID = "DWK264"
PASSWORD = "master.1"
TOTP_SECRET = "AVU7NJKPBH27FKNCMCWMFPMZ7NKQFXUY"

options = Options()
options.add_argument("--headless=new")
options.add_argument("--window-size=1280,720")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

print("Starting headless Edge browser...")
driver = webdriver.Edge(options=options)
wait = WebDriverWait(driver, 15)

try:
    login_url = f"https://kite.zerodha.com/connect/login?api_key={API_KEY}&v=3"
    print(f"Step 1: Opening {login_url[:60]}...")
    driver.get(login_url)
    time.sleep(2)
    driver.save_screenshot("debug_step1_login.png")

    print("Step 2: Entering credentials...")
    user_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']")))
    user_field.send_keys(USER_ID)
    pass_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
    pass_field.send_keys(PASSWORD)
    
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    print("  Login submitted...")
    time.sleep(3)
    driver.save_screenshot("debug_step2_after_login.png")

    print("Step 3: Entering TOTP...")
    totp = pyotp.TOTP(TOTP_SECRET)
    code = totp.now()
    print(f"  TOTP code: {code}")
    
    totp_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[type='number'], input[autocomplete='one-time-code']")))
    totp_field.send_keys(code)
    time.sleep(1)
    
    driver.save_screenshot("debug_step3_before_totp_submit.png")
    
    try:
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        print("  TOTP submitted...")
    except:
        print("  TOTP auto-submitted...")
    
    time.sleep(5)
    driver.save_screenshot("debug_step4_after_totp.png")

    current_url = driver.current_url
    print(f"Step 4: Current URL: {current_url[:100]}")
    
    if "authorize" in current_url:
        print("  Authorize page detected, clicking approve...")
        try:
            auth_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit'], .button-blue, button.btn")))
            auth_btn.click()
            time.sleep(3)
        except:
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if "authorize" in btn.text.lower() or "approve" in btn.text.lower() or "continue" in btn.text.lower():
                    btn.click()
                    time.sleep(3)
                    break
    
    driver.save_screenshot("debug_step5_final.png")
    final_url = driver.current_url
    print(f"Step 5: Final URL: {final_url[:150]}")

    if "request_token=" in final_url:
        parsed = urllib.parse.urlparse(final_url)
        params = urllib.parse.parse_qs(parsed.query)
        request_token = params.get("request_token", [None])[0]
        print(f"\n  request_token: {request_token}")
        print("\n=== SUCCESS ===")
    else:
        print(f"\nFAILED - URL doesn't contain request_token")
        
finally:
    driver.quit()
    print("Browser closed.")
