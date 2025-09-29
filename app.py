import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urlparse
import concurrent.futures

def get_main_domain(url):
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme or 'https'
    domain = parsed_url.netloc
    return f"{scheme}://{domain}/"

def detect_signin_wall(soup):
    keywords = [
        'login', 'sign in', 'sign-in', 'signin', 'sign up', 'sign-up', 'signup',
        'register', 'create account', 'authentication required', 'members only',
        'please sign in', 'account required', 'access denied', 'please log in',
        'to continue, please', 'to read this', 'to access this', 'subscribe to read',
        'log in to view', 'sign in to access', 'register to read', 'sign in to continue'
    ]
    overlays = soup.find_all(['div', 'section'], style=True)
    for overlay in overlays:
        style = overlay.get('style', '').lower()
        if 'position: fixed' in style or 'position: absolute' in style:
            text = overlay.get_text(separator=' ', strip=True).lower()
            if any(k in text for k in keywords):
                return 'Yes'
    forms = soup.find_all('form')
    for form in forms:
        form_text = form.get_text(separator=' ', strip=True).lower()
        if any(k in form_text for k in keywords):
            return 'Yes'
    main_content = soup.find(['article', 'main'])
    if main_content and len(main_content.get_text(strip=True)) > 100:
        return 'No'
    page_text = soup.get_text(separator=' ', strip=True).lower()
    for phrase in ['please sign in to continue', 'sign in to access', 'register to read', 'log in to view']:
        if phrase in page_text:
            return 'Yes'
    return 'No'

def classify_domain(url):
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, timeout=10, headers=headers)
        status_code = response.status_code
        final_url = response.url
        parsed_initial = urlparse(url)
        parsed_final = urlparse(final_url)
        if parsed_initial.netloc != parsed_final.netloc and parsed_final.netloc.endswith(parsed_initial.netloc):
            main_domain_url = get_main_domain(final_url)
            response = requests.get(main_domain_url, timeout=10, headers=headers)
            status_code = response.status_code
            url = main_domain_url
        if status_code in [400, 404, 500, 502, 503, 504]:
            return url, f"Not Working (HTTP {status_code})", "No"
        if status_code == 401:
            return url, "Manual Check Required (Sign-in needed)", "Yes"
        if status_code == 403:
            return url, "Manual Check Required (Forbidden)", "Yes"
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a', href=True)
        signin_needed = detect_signin_wall(soup)
        if not links:
            return url, "Nofollow (No links found)", signin_needed
        for link in links:
            rel = link.get('rel')
            if rel and any(r.lower() == 'nofollow' for r in rel):
                return url, "Nofollow", signin_needed
        return url, "Dofollow", signin_needed
    except requests.exceptions.RequestException as e:
        err_str = str(e).lower()
        captcha_keywords = ['captcha', 'bot verification', 'verify you are human', 'are you a robot', 'security check']
        if any(word in err_str for word in captcha_keywords):
            return url, "Manual Check Required (CAPTCHA or Bot Verification)", "Yes"
        if '401' in err_str or 'unauthorized' in err_str or 'forbidden' in err_str:
            return url, "Manual Check Required (Sign-in needed)", "Yes"
        return url, f"Error - {str(e)}", "No"

st.title("Bulk Domain Link Checker")
st.write("Paste up to 100 URLs below (one per line):")
urls_input = st.text_area("URLs", "", height=200)

if st.button("Check Links"):
    urls = [u.strip() for u in urls_input.splitlines() if u.strip()]
    if len(urls) > 100:
        st.warning("Maximum of 100 URLs allowed.")
    elif not urls:
        st.warning("Please enter at least one URL.")
    else:
        with st.spinner("Processing URLs, please wait..."):
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(classify_domain, urls))
        df = pd.DataFrame(results, columns=["Domain URL", "Link Type", "Sign-in Needed"])
        st.dataframe(df)
        st.download_button("Download CSV", df.to_csv(index=False), "domain_link_classification.csv")
