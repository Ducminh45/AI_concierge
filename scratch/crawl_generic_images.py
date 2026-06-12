import urllib.request
import json
import urllib.parse
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def search_wiki_images(query):
    print(f"Searching Wikimedia Commons for: {query}")
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&srnamespace=6&format=json"
    
    try:
        req = urllib.request.Request(search_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            search_data = json.loads(response.read().decode('utf-8'))
            search_results = search_data.get('query', {}).get('search', [])
            
            if not search_results:
                return []
            
            titles = "|".join([res['title'] for res in search_results[:10]])
            encoded_titles = urllib.parse.quote(titles)
            info_url = f"https://commons.wikimedia.org/w/api.php?action=query&titles={encoded_titles}&prop=imageinfo&iiprop=url&format=json"
            
            info_req = urllib.request.Request(info_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(info_req) as info_resp:
                info_data = json.loads(info_resp.read().decode('utf-8'))
                pages = info_data.get('query', {}).get('pages', {})
                
                images = []
                for page_id, page_info in pages.items():
                    imageinfo = page_info.get('imageinfo', [])
                    if imageinfo:
                        images.append({
                            'title': page_info.get('title'),
                            'url': imageinfo[0].get('url')
                        })
                return images
                
    except Exception as e:
        print(f"Error searching images for {query}: {e}")
        return []

topics = [
    "Luxury hotel room bed",
    "Waterpark resort",
    "Luxury swimming pool resort",
    "Vinpearl resort"
]

all_images = {}
for topic in topics:
    images = search_wiki_images(topic)
    if images:
        all_images[topic] = images
        print(f"Found {len(images)} images for {topic}")
    else:
        print(f"No images found for {topic}")

with open("generic_images.json", "w", encoding="utf-8") as f:
    json.dump(all_images, f, ensure_ascii=False, indent=2)
print("Saved to generic_images.json")
