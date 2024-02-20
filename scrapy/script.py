from bs4 import BeautifulSoup
import requests
import json

def getAvatars():

# Replace 'url' with the URL of the web page you want to scrape
    url = 'https://www.iconfinder.com/avatar-icons?category=avatar&price=free&license=gte__1'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    img_urls = []

# Find all elements with class name "foobar"
    elements = soup.find_all(class_='icon-preview-img d-flex align-items-center justify-content-center')

# Iterate over the found elements
    for element in elements:
        # Find the img tag inside the div
        img_tag = element.find('img')
        
        # Check if the img tag exists
        if img_tag:
            # Get the src attribute value
            src_value = img_tag.get('src')
            img_urls.append(src_value)
    with open('avatars.json', 'w') as f:
        json.dump(img_urls, f)

