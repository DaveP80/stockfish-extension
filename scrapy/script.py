from bs4 import BeautifulSoup
import requests
import json
import re
def getAvatars():

    img_urls = []
    for i in range(3):

        url = f"https://www.iconfinder.com/avatar-icons?category=avatar&price=free&license=gte__{i}"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')

        elements = soup.find_all(class_=re.compile(r'icon-preview '))

# Iterate over the found elements
        for element in elements:
            # Find the img tag inside the div
            img_tag = element.find('img', recursive=True)
            a_tag = element.find("a", recursive=True)
            src_value = None
            href_value = None
            if img_tag:
                # Get the src attribute value
                src_value = img_tag.get('src')
                href_value = img_tag.get('href')
                if src_value and "istock" not in src_value and src_value not in img_urls:
                    img_urls.append(src_value)
                elif href_value and "istock" not in href_value and href_value not in img_urls:
                    img_urls.append(href_value)
            elif a_tag:
                src_value = img_tag.get('src')
                href_value = img_tag.get('href')
                if src_value and "istock" not in src_value and src_value not in img_urls:
                    img_urls.append(src_value)
                elif href_value and "istock" not in href_value and href_value not in img_urls:
                    img_urls.append(href_value)

    with open('newavatars.json', 'w') as f:
        json.dump(img_urls, f)
